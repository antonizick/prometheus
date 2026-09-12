#!/usr/bin/env python3
"""Replay harness — interest scoring over journalled history.

Answers "what would this have said?" against real desktop history, without
speaking anything and without waiting a week to find out.

    experiments/replay-scoring.py                   # current config
    experiments/replay-scoring.py --verbose         # every decision, with reasons
    experiments/replay-scoring.py --rate 0.05       # what 5% would have felt like
    experiments/replay-scoring.py --compare         # old scoring vs new, side by side
    experiments/replay-scoring.py --verbosity quiet # what a tier actually yields
    experiments/replay-scoring.py --hourly          # utterances per hour, worst hour
    experiments/replay-scoring.py --since 2026-09-11T18:00:00

The scoring itself lives in `bin/prometheus-attention` and is imported, not
reimplemented — the live path (`prometheus-hypr`) imports the same file. A
harness that only approximates the real rules is worse than no harness, because
it produces confident numbers about a system that doesn't exist.

Two passes, both read-only:

  Pass 1 walks the journal chronologically and scores each event using only
  what is known at that point — no lookahead, exactly as the live path sees it.
  Workspace bursts are settled first (see `settle_workspaces`).

  Pass 2 solves for the gain that lands the achieved rate on the target, then
  re-walks applying the quiet-period floor and repetition penalties in
  simulated order, drawing from a seeded RNG so runs are reproducible.

`--compare` reproduces the pre-Phase-5 scoring alongside the current one. That
is what the Phase 5 weight changes were argued from, and re-running it is how
you check the argument still holds on a longer journal.
"""

from __future__ import annotations

import argparse
import collections
import datetime
import importlib.machinery
import importlib.util
import json
import os
import random
import sys

HOME = os.path.expanduser("~")
CONFIG_DIR = os.environ.get("PROMETHEUS_CONFIG_DIR") or os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or f"{HOME}/.config", "prometheus")
STATE_DIR = os.environ.get("PROMETHEUS_STATE_DIR") or os.path.join(
    os.environ.get("XDG_STATE_HOME") or f"{HOME}/.local/state", "prometheus")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
DEFAULT_JOURNAL = os.path.join(STATE_DIR, "journal")

BIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin")


def load_attention_module():
    path = os.path.normpath(os.path.join(BIN_DIR, "prometheus-attention"))
    loader = importlib.machinery.SourceFileLoader("prometheus_attention", path)
    spec = importlib.util.spec_from_loader("prometheus_attention", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


A = load_attention_module()


# --------------------------------------------------------------------------
# The pre-Phase-5 scoring, kept verbatim for --compare
# --------------------------------------------------------------------------

LEGACY_ATTENTION = {
    "novelty_boost": 2.0, "rarity_boost": 1.5, "odd_hour_boost": 1.8,
    "recent_speech_penalty": 0.15, "repetition_penalty": 0.4,
    "rapid_switch_penalty": 0.1, "quiet_period_secs": 45,
}
LEGACY_SCORED_KINDS = ("open", "close", "focus", "fullscreen")
LEGACY_ABSENCE_GAP_SECS = 3600


def legacy_score(events: list[dict], attn: dict) -> list[dict]:
    counts: collections.Counter = collections.Counter()
    seen_today: dict[str, str] = {}
    last_any_t: float | None = None
    scored = []
    for e in events:
        if e.get("kind") not in LEGACY_SCORED_KINDS:
            continue
        app = e.get("name") or e.get("cls")
        if not app:
            continue
        t = e.get("t", 0)
        day = datetime.date.fromtimestamp(t).isoformat()
        hour = datetime.datetime.fromtimestamp(t).hour
        raw, reasons = 1.0, []
        if seen_today.get(app) != day:
            raw *= attn["novelty_boost"]; reasons.append("novel-today")
        if counts[app] <= A.RARE_THRESHOLD:
            raw *= attn["rarity_boost"]; reasons.append("rare")
        if hour < 6 or hour >= 23:
            raw *= attn["odd_hour_boost"]; reasons.append("odd-hour")
        if last_any_t is not None and (t - last_any_t) > LEGACY_ABSENCE_GAP_SECS:
            raw *= attn["novelty_boost"]; reasons.append("returned")
        co = e.get("coalesced") or 0
        if co > 1:
            raw *= attn["rapid_switch_penalty"]; reasons.append(f"rapid-switch(x{co})")
        scored.append({"t": t, "kind": e["kind"], "app": app, "raw": raw,
                       "reasons": reasons})
        counts[app] += 1
        seen_today[app] = day
        last_any_t = t
    return scored


def legacy_decide(scored: list[dict], attn: dict, target_rate: float,
                  seed: int) -> list[dict]:
    """The old constant-gain normalization: k = target / mean(raw), applied once."""
    if not scored:
        return []
    mean_raw = sum(s["raw"] for s in scored) / len(scored)
    k = (target_rate / mean_raw) if mean_raw > 0 else 0.0
    rng = random.Random(seed)
    gate = A.Gate(attn)
    out = []
    for s in scored:
        prob, g = gate.apply(s["t"], s["app"], min(1.0, s["raw"] * k))
        spoke = rng.random() < prob
        if spoke:
            gate.record_spoken(s["t"], s["app"])
        out.append({**s, "prob": prob, "gate": g, "would_speak": spoke})
    return out


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

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


def load_config() -> dict:
    try:
        with open(CONFIG_FILE) as f:
            return json.loads(strip_jsonc(f.read()))
    except (OSError, ValueError):
        return {}


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
# Current scoring
# --------------------------------------------------------------------------

def score_current(events: list[dict], attn: dict, kinds: set,
                  require_reason: set) -> list[dict]:
    """Score every event, return only the ones this verbosity may speak about.

    The scorer is fed *everything*, including kinds the current tier will never
    narrate. Verbosity controls what it talks about, not what it knows — a
    focus change still counts as activity for "returned after an absence" even
    at `quiet`, where focus changes are never spoken. Filtering before scoring
    was the first cut here and it silently broke dwell tracking: with focus
    events removed, `last_focus_t` never advanced and `long-dwell` never fired.
    """
    scorer = A.Scorer(attn)
    scored = []
    for e in events:
        kind = e.get("kind")
        if kind not in A.SCORED_KINDS:
            continue
        app = A.event_app(e)
        if not app:
            continue
        t = e.get("t", 0)
        s = scorer.score(t, kind, app, e.get("coalesced") or 0)
        if kind not in kinds:
            continue
        if kind in require_reason and not A.meaningful_reasons(s["reasons"]):
            continue
        scored.append({"t": t, "kind": kind, "app": app, **s})
    return scored


def decide(scored: list[dict], attn: dict, k: float, seed: int) -> list[dict]:
    rng = random.Random(seed)
    gate = A.Gate(attn)
    out = []
    for s in scored:
        prob, g = gate.apply(s["t"], s["app"], min(1.0, s["raw"] * k))
        spoke = rng.random() < prob
        if spoke:
            gate.record_spoken(s["t"], s["app"])
        out.append({**s, "prob": prob, "gate": g, "would_speak": spoke})
    return out


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def signal_census(scored: list[dict]) -> list[tuple[str, int]]:
    c: collections.Counter = collections.Counter()
    for s in scored:
        for r in s["reasons"]:
            c[r.split("(")[0]] += 1
    return c.most_common()


def report_hourly(spoken: list[dict]) -> None:
    by_hour: collections.Counter = collections.Counter()
    for d in spoken:
        by_hour[datetime.datetime.fromtimestamp(d["t"]).strftime("%H")] += 1
    if not by_hour:
        print("hourly         : nothing spoken")
        return
    print("hourly         :")
    for h in sorted(by_hour):
        bar = "#" * by_hour[h]
        print(f"    {h}:00  {by_hour[h]:>3}  {bar}")
    worst = by_hour.most_common(1)[0]
    print(f"    worst hour: {worst[0]}:00 with {worst[1]}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--journal", default=DEFAULT_JOURNAL)
    ap.add_argument("--rate", type=float, default=None,
                    help="override speak.desktop_activity.target_rate")
    ap.add_argument("--since", default=None,
                    help="unix timestamp or ISO datetime; default: whole journal")
    ap.add_argument("--verbosity", default=None,
                    choices=sorted(A.VERBOSITY_KINDS),
                    help="which event kinds are eligible; default: config")
    ap.add_argument("--settle", type=float, default=None,
                    help="workspace settle window; default: hypr.workspace_settle_secs")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--compare", action="store_true",
                    help="also run the pre-Phase-5 scoring, for contrast")
    ap.add_argument("--hourly", action="store_true", help="utterances per hour")
    ap.add_argument("-v", "--verbose", action="store_true", help="print every decision")
    a = ap.parse_args()

    cfg = load_config()
    attn = A.attention_from_config(cfg)
    target_rate = a.rate if a.rate is not None else A.target_rate_from_config(cfg)
    verbosity = a.verbosity or cfg.get("verbosity", "normal")
    kinds = A.kinds_for_verbosity(verbosity, cfg)
    require_reason = A.require_reason_kinds(cfg)
    hypr = cfg.get("hypr") or {}
    settle = a.settle if a.settle is not None else float(
        hypr.get("workspace_settle_secs",
                 max(2.0, float(hypr.get("debounce_secs", 1.5)))))

    events = load_journal(a.journal, parse_since(a.since))
    if not events:
        print("no journal events in range — nothing to replay")
        return 0

    raw_workspace = sum(1 for e in events if e.get("kind") == "workspace")
    events = A.settle_workspaces(events, settle)
    settled_workspace = sum(1 for e in events if e.get("kind") == "workspace")

    scored = score_current(events, attn, kinds, require_reason)
    if not scored:
        print(f"no scorable events at verbosity={verbosity} — nothing to replay")
        return 0
    k = A.solve_k(scored, attn, target_rate, a.seed)
    decided = decide(scored, attn, k, a.seed)
    spoken = [d for d in decided if d["would_speak"]]

    if a.verbose:
        for d in decided:
            ts = datetime.datetime.fromtimestamp(d["t"]).strftime("%H:%M:%S")
            mark = "SPEAK" if d["would_speak"] else "  .  "
            print(f"{ts} [{mark}] {d['kind']:<10} {d['app']:<20} "
                  f"prob={d['prob']:.3f} gate={d['gate']:<13} "
                  f"{','.join(d['reasons']) or '-'}")

    span = (events[-1]["t"] - events[0]["t"]) if len(events) > 1 else 0
    hours = span / 3600 or 1e-9

    print()
    print(f"journal        : {a.journal}")
    print(f"window         : {span / 60:.1f} min ({hours:.1f} h), "
          f"{len(events)} events after settling")
    print(f"verbosity      : {verbosity}  (kinds: {', '.join(sorted(kinds))})")
    gated = sorted(kinds & require_reason)
    if gated:
        print(f"needs a reason : {', '.join(gated)} "
              f"(never spoken on a bare draw)")
    print(f"workspace      : {raw_workspace} switches -> {settled_workspace} landings "
          f"(settle {settle}s)")
    print(f"target rate    : {target_rate:.0%}   gain k={k:.3f}")
    print(f"would speak    : {len(spoken)}/{len(scored)} "
          f"({len(spoken) / len(scored) * 100:.1f}% achieved)")
    print(f"               : {len(spoken) / hours:.1f} utterances/hour")

    with_signal = sum(1 for d in spoken if d["reasons"])
    print(f"carried a reason: {with_signal}/{len(spoken)} "
          f"({(with_signal / len(spoken) * 100) if spoken else 0:.0f}% — "
          f"the rest are bare draws at the base rate)")

    print("signal census  : (how often each fired across all scorable events)")
    for name, n in signal_census(scored):
        print(f"    {name:<16} {n:>4}/{len(scored)}  ({n / len(scored) * 100:5.1f}%)")

    by_app = collections.Counter(d["app"] for d in spoken)
    if by_app:
        print("by app         :")
        for app, n in by_app.most_common(10):
            print(f"    {n:>3}  {app}")

    if a.hourly:
        report_hourly(spoken)

    if a.compare:
        legacy_events = load_journal(a.journal, parse_since(a.since))
        ls = legacy_score(legacy_events, LEGACY_ATTENTION)
        ld = legacy_decide(ls, LEGACY_ATTENTION, target_rate, a.seed)
        lspoken = [d for d in ld if d["would_speak"]]
        lws = sum(1 for e in legacy_events if e.get("kind") == "workspace")
        lsig = sum(1 for d in lspoken if d["reasons"])
        print()
        print("--- pre-Phase-5 scoring, same journal ---")
        print(f"would speak    : {len(lspoken)}/{len(ls)} "
              f"({len(lspoken) / len(ls) * 100:.1f}% achieved, target {target_rate:.0%})")
        print(f"               : {len(lspoken) / hours:.1f} utterances/hour, "
              f"plus {lws} workspace switches spoken unconditionally "
              f"= {(len(lspoken) + lws) / hours:.1f}/hour")
        print(f"carried a reason: {lsig}/{len(lspoken)} "
              f"({(lsig / len(lspoken) * 100) if lspoken else 0:.0f}%)")
        print("signal census  :")
        for name, n in signal_census(ls):
            print(f"    {name:<16} {n:>4}/{len(ls)}  ({n / len(ls) * 100:5.1f}%)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
