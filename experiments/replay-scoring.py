#!/usr/bin/env python3
"""Replay harness — interest scoring over journalled history (docs/04, tasks
1.7-1.8; weights documented in docs/08-personality-and-config.md).

Runs the "would this have been spoken?" decision over
~/.local/state/prometheus/journal without speaking anything. Phase 1 builds no
live narration (docs/04: "no narration yet ... collecting data first") — this
is the offline tool that makes the eventual narration policy *evidence-based*
instead of guessed, by replaying real desktop history against the attention
weights already scaffolded in config.json.

    experiments/replay-scoring.py                  # journal, default weights
    experiments/replay-scoring.py --verbose         # per-event decisions
    experiments/replay-scoring.py --rate 0.05       # try a different target
    experiments/replay-scoring.py --since 2026-09-11T00:00:00

Two passes over the journal, both read-only:

  Pass 1 walks it chronologically and scores every open/close/focus/
  fullscreen event against novelty, rarity, odd-hour and rapid-switch
  signals, using only what's known *up to that point* — no lookahead.
  workspace events aren't scored; docs/01 puts workspace switches in the
  `quiet` tier, i.e. always-on, so they're reported separately as a fixed
  baseline rather than run through the probability gate.

  Pass 2 re-walks the scored events, scales every raw score by a constant so
  the mean selection probability lands on the target rate (docs/08: "interest
  ranking and volume are independent dials"), then applies the hard
  quiet-period floor and repetition/recency penalties *in simulated order*
  (a penalty depends on what the simulation already decided to "speak"), and
  draws each decision from a seeded RNG for reproducibility.

"Return after absence" reuses novelty_boost rather than a dedicated config
weight — config.json's attention block doesn't have a separate one, and
inventing an unconfigured knob would make this drift from what's actually
tunable. Sequence-oddity scoring from docs/08's table isn't implemented for
the same reason: no weight exists for it yet.
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
import os
import random
import sys
import time

HOME = os.path.expanduser("~")
CONFIG_DIR = os.environ.get("PROMETHEUS_CONFIG_DIR") or os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or f"{HOME}/.config", "prometheus")
STATE_DIR = os.environ.get("PROMETHEUS_STATE_DIR") or os.path.join(
    os.environ.get("XDG_STATE_HOME") or f"{HOME}/.local/state", "prometheus")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
DEFAULT_JOURNAL = os.path.join(STATE_DIR, "journal")

DEFAULT_ATTENTION = {
    "novelty_boost": 2.0,
    "rarity_boost": 1.5,
    "odd_hour_boost": 1.8,
    "recent_speech_penalty": 0.15,
    "repetition_penalty": 0.4,
    "rapid_switch_penalty": 0.1,
    "quiet_period_secs": 45,
}
DEFAULT_TARGET_RATE = 0.15

SCORED_KINDS = ("open", "close", "focus", "fullscreen")
RARE_THRESHOLD = 2          # at most this many prior sightings still counts as rare
ABSENCE_GAP_SECS = 3600     # gap since any event that counts as "returning"
REPETITION_WINDOW_SECS = 600
SOFT_SUPPRESS_MULT = 3      # x quiet_period_secs: fades from hard floor to normal


def strip_jsonc(text: str) -> str:
    out, in_str, esc, i = [], False, False, 0
    while i < len(text):
        c = text[i]
        if in_str:
            out.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
            out.append(c)
        elif c == "/" and i + 1 < len(text) and text[i + 1] == "/":
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        else:
            out.append(c)
        i += 1
    return "".join(out)


def load_attention_and_rate() -> tuple[dict, float]:
    try:
        with open(CONFIG_FILE) as f:
            raw = json.loads(strip_jsonc(f.read()))
    except (OSError, ValueError):
        raw = {}
    attention = dict(DEFAULT_ATTENTION)
    attention.update(raw.get("attention", {}))
    rate = raw.get("speak", {}).get("desktop_activity", {}).get("target_rate", DEFAULT_TARGET_RATE)
    return attention, float(rate)


def load_journal(path: str, since_ts: float | None) -> list[dict]:
    events = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if since_ts is not None and rec.get("t", 0) < since_ts:
                    continue
                events.append(rec)
    except OSError:
        print(f"no journal at {path}", file=sys.stderr)
    events.sort(key=lambda r: r.get("t", 0))
    return events


def parse_since(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        pass
    return datetime.datetime.fromisoformat(s).timestamp()


# --------------------------------------------------------------------------
# Pass 1 — raw interest score, no lookahead
# --------------------------------------------------------------------------

def score_events(events: list[dict], attn: dict) -> list[dict]:
    counts_total: dict[str, int] = collections.Counter()
    seen_today: dict[str, str] = {}   # app -> date string of last-seen day
    last_any_t: float | None = None
    scored = []

    for e in events:
        if e.get("kind") not in SCORED_KINDS:
            continue
        app = e.get("name") or e.get("cls")
        if not app:
            continue
        t = e.get("t", 0)
        day = datetime.date.fromtimestamp(t).isoformat()
        hour = datetime.datetime.fromtimestamp(t).hour

        raw = 1.0
        reasons = []

        if seen_today.get(app) != day:
            raw *= attn["novelty_boost"]
            reasons.append("novel-today")
        if counts_total[app] <= RARE_THRESHOLD:
            raw *= attn["rarity_boost"]
            reasons.append("rare")
        if hour < 6 or hour >= 23:
            raw *= attn["odd_hour_boost"]
            reasons.append("odd-hour")
        if last_any_t is not None and (t - last_any_t) > ABSENCE_GAP_SECS:
            raw *= attn["novelty_boost"]
            reasons.append("returned")
        coalesced = e.get("coalesced") or 0
        if coalesced > 1:
            raw *= attn["rapid_switch_penalty"]
            reasons.append(f"rapid-switch(x{coalesced})")

        scored.append({"t": t, "kind": e["kind"], "app": app, "raw": raw, "reasons": reasons})

        counts_total[app] += 1
        seen_today[app] = day
        last_any_t = t

    return scored


# --------------------------------------------------------------------------
# Pass 2 — normalize to the target rate, apply quiet-period + repetition,
# draw decisions in simulated chronological order
# --------------------------------------------------------------------------

def decide(scored: list[dict], attn: dict, target_rate: float, seed: int) -> list[dict]:
    if not scored:
        return []
    mean_raw = sum(s["raw"] for s in scored) / len(scored)
    k = (target_rate / mean_raw) if mean_raw > 0 else 0.0

    rng = random.Random(seed)
    quiet = float(attn["quiet_period_secs"])
    last_spoken_t: float | None = None
    recent: collections.deque[tuple[float, str]] = collections.deque()  # (t, app), spoken only

    out = []
    for s in scored:
        t, app = s["t"], s["app"]
        prob = min(1.0, s["raw"] * k)

        while recent and t - recent[0][0] > REPETITION_WINDOW_SECS:
            recent.popleft()
        recent_count = sum(1 for (_, a) in recent if a == app)
        if recent_count:
            prob *= attn["repetition_penalty"] ** recent_count

        gate = "open"
        if last_spoken_t is not None:
            gap = t - last_spoken_t
            if gap < quiet:
                prob = 0.0
                gate = "quiet_period"
            elif gap < quiet * SOFT_SUPPRESS_MULT:
                prob *= attn["recent_speech_penalty"]
                gate = "recent_speech"

        prob = max(0.0, min(1.0, prob))
        would_speak = rng.random() < prob
        if would_speak:
            last_spoken_t = t
            recent.append((t, app))

        out.append({**s, "prob": prob, "gate": gate, "would_speak": would_speak})
    return out


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--journal", default=DEFAULT_JOURNAL)
    ap.add_argument("--rate", type=float, default=None,
                    help="override speak.desktop_activity.target_rate")
    ap.add_argument("--since", default=None,
                    help="unix timestamp or ISO datetime; default: whole journal")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("-v", "--verbose", action="store_true", help="print every decision")
    a = ap.parse_args()

    attn, cfg_rate = load_attention_and_rate()
    target_rate = a.rate if a.rate is not None else cfg_rate
    since_ts = parse_since(a.since)

    events = load_journal(a.journal, since_ts)
    if not events:
        print("no journal events in range — nothing to replay")
        return 0

    workspace_switches = sum(1 for e in events if e.get("kind") == "workspace")
    scored = score_events(events, attn)
    decided = decide(scored, attn, target_rate, a.seed)

    if a.verbose:
        for d in decided:
            ts = datetime.datetime.fromtimestamp(d["t"]).strftime("%H:%M:%S")
            mark = "SPEAK" if d["would_speak"] else "  .  "
            reasons = ",".join(d["reasons"]) or "-"
            print(f"{ts} [{mark}] {d['kind']:<10} {d['app']:<20} "
                  f"prob={d['prob']:.3f} gate={d['gate']:<13} {reasons}")

    spoken = [d for d in decided if d["would_speak"]]
    by_app = collections.Counter(d["app"] for d in spoken)

    span = (events[-1]["t"] - events[0]["t"]) if len(events) > 1 else 0
    print()
    print(f"journal        : {a.journal}")
    print(f"window         : {span / 60:.1f} min, {len(events)} raw events "
          f"({workspace_switches} workspace, {len(scored)} scorable)")
    print(f"target rate    : {target_rate:.0%}")
    print(f"would speak    : {len(spoken)}/{len(scored)}"
          f" ({(len(spoken) / len(scored) * 100) if scored else 0:.1f}% achieved)")
    print(f"+ workspace    : always spoken (quiet-tier baseline), {workspace_switches} more")
    if by_app:
        print("by app         :")
        for app, n in by_app.most_common(10):
            print(f"    {n:>3}  {app}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
