#!/usr/bin/env python3
"""Stage a listening review of the phrase bank (Phase 2, task 2.10).

  experiments/build-phrasebook-audio.py              # everything, default mix
  experiments/build-phrasebook-audio.py --per-event 6
  experiments/build-phrasebook-audio.py --events command_failed,claude_blocked

docs/04's review gate: "before any narration is wired into the live desktop,
the candidate phrasings get synthesized to audio and listened to. Text that
reads fine on screen frequently sounds wrong."

This writes WAV files and an index. **It plays nothing.** Nick decides when
sound comes out of his machine — `experiments/phrasebook/play.sh` does that,
and says so before it starts.

Two things are staged, because they answer different questions:

  by-event/   every sampled phrasing for one moment, back to back. Answers
              "do these all sound like the same system, and would I still be
              happy hearing the fortieth?"
  session/    a plausible hour of work, in the order it would actually occur,
              with the real gaps compressed. Answers the only question that
              really matters: "would I turn this off?"

Seed lines (hand-written) and model lines (written by the authoring model) are
labelled in the index and ordered so they alternate, so the difference between
them is audible rather than something you have to take on trust.
"""
from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import json
import os
import random
import subprocess
import sys
import wave

HOME = os.path.expanduser("~")
REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
OUT_DIR = os.path.join(REPO, "experiments", "phrasebook")
VOICES = os.path.join(HOME, ".local/share/piper/voices")
PIPER = "/opt/piper-tts/piper"
ESPEAK = "/opt/piper-tts/espeak-ng-data"
LENGTH_SCALE = "0.7"          # locked, docs/08

SYSTEM_VOICE = "en_GB-alan-medium"
AGENT_VOICE = "en_GB-alba-medium"
# config.json's voice.category_map sends the claude category to the second
# voice, so the review has to hear those in the voice they'll actually use.
AGENT_EVENTS = {"claude_blocked", "claude_blocked_project", "claude_finished"}

# Realistic values, not the spec's generation examples — this is about how the
# phrasings land with the names Nick will really hear.
SLOTS = {
    "app": ["Brave", "the terminal", "Claude Code", "Obsidian"],
    "workspace": ["3", "1", "5"],
    "command": ["the build", "the tests", "the install"],
    "duration": ["forty seconds", "two minutes"],
    "project": ["Prometheus", "ASCII Art Studio"],
    "percent": ["ten percent", "fifteen percent"],
    "span": ["fifteen minutes", "half an hour"],
}

# One plausible stretch of a working day, in order. (event, slot overrides)
SESSION = [
    ("toggled_on", {}),
    ("app_first_today", {"app": "Brave"}),
    ("workspace_switched", {"workspace": "2"}),
    ("app_opened", {"app": "the terminal"}),
    ("command_failed", {"command": "the build"}),
    ("app_returned", {"app": "Claude Code"}),
    ("claude_blocked", {}),
    ("command_succeeded_long", {"command": "the tests", "duration": "two minutes"}),
    ("workspace_switched", {"workspace": "4"}),
    ("app_rare", {"app": "Kdenlive"}),
    ("claude_blocked_project", {"project": "Prometheus"}),
    ("monitor_connected", {}),
    ("brief_empty", {"span": "half an hour"}),
    ("battery_low", {"percent": "fifteen percent"}),
    ("app_odd_hour", {"app": "the terminal"}),
    ("claude_finished", {}),
    ("toggled_off", {}),
]


def load_phrasebank_module():
    """Reuse the real renderer rather than reimplementing slot substitution —
    a review that renders differently from the runtime is reviewing fiction."""
    path = os.path.join(REPO, "bin", "prometheus-phrasebank")
    loader = importlib.machinery.SourceFileLoader("pb", path)
    spec = importlib.util.spec_from_loader("pb", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def synth(text: str, voice: str, out_path: str) -> float:
    """One WAV at the real playback settings. Returns its duration."""
    model = os.path.join(VOICES, voice + ".onnx")
    proc = subprocess.run(
        [PIPER, "--model", model, "--output_file", out_path,
         "--length_scale", LENGTH_SCALE, "--sentence_silence", "0.2",
         "--espeak_data", ESPEAK, "--quiet"],
        input=text.encode(), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        print(f"  piper failed on {text!r}: {proc.stderr.decode()[:200]}", file=sys.stderr)
        return 0.0
    with wave.open(out_path) as w:
        return w.getnframes() / float(w.getframerate())


def concat(paths: list[str], out_path: str, gap_secs: float = 0.9) -> float:
    """Glue clips together with a gap, so a sequence can be played as one file
    by anything, including a phone."""
    params, frames = None, []
    for i, p in enumerate(paths):
        with wave.open(p) as w:
            if params is None:
                params = w.getparams()
            frames.append(w.readframes(w.getnframes()))
        if i != len(paths) - 1:
            silence = b"\x00" * int(params.framerate * gap_secs) * params.sampwidth * params.nchannels
            frames.append(silence)
    with wave.open(out_path, "wb") as w:
        w.setparams(params)
        for f in frames:
            w.writeframes(f)
    with wave.open(out_path) as w:
        return w.getnframes() / float(w.getframerate())


def interleave(variants: list[dict], n: int, rnd: random.Random) -> list[dict]:
    """Alternate seed and model lines so the difference is audible in sequence
    rather than arriving in two blocks."""
    seeds = [v for v in variants if v["src"] == "seed"]
    model = [v for v in variants if v["src"] == "model"]
    rnd.shuffle(seeds)
    rnd.shuffle(model)
    out = []
    while len(out) < n and (seeds or model):
        for pool in (seeds, model):
            if pool and len(out) < n:
                out.append(pool.pop())
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-event", type=int, default=6)
    ap.add_argument("--events", default=None)
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args()

    pb = load_phrasebank_module()
    bank = pb.load_bank_raw()
    if not bank:
        print("no phrase bank — run `prometheus regenerate` first", file=sys.stderr)
        return 1
    if not os.path.isdir(VOICES):
        print(f"no voices in {VOICES}", file=sys.stderr)
        return 1

    rnd = random.Random(a.seed)
    by_event = os.path.join(OUT_DIR, "by-event")
    session = os.path.join(OUT_DIR, "session")
    for d in (by_event, session):
        os.makedirs(d, exist_ok=True)

    wanted = list(bank["events"])
    if a.events:
        wanted = [e.strip() for e in a.events.split(",") if e.strip()]

    index = ["# Phrase-bank listening review",
             "",
             f"Bank written {bank['generated_at_iso']} by "
             f"`{bank['inputs']['authoring_model']}`, register "
             f"`{bank['inputs']['register']}`, name `{bank['inputs']['name']}`.",
             "",
             "`*` = hand-written seed · `~` = written by the authoring model.",
             "",
             "Play with `experiments/phrasebook/play.sh` — **it makes sound**.",
             ""]
    total_secs = 0.0

    for eid in wanted:
        ev = bank["events"].get(eid)
        if not ev:
            print(f"unknown event {eid}", file=sys.stderr)
            continue
        picks = interleave(ev["variants"], a.per_event, rnd)
        voice = AGENT_VOICE if eid in AGENT_EVENTS else SYSTEM_VOICE
        index.append(f"## {eid}  ({len(ev['variants'])} in the bank, "
                     f"{a.per_event} sampled, voice `{voice}`)")
        index.append("")
        clips = []
        for i, v in enumerate(picks, 1):
            slots = {s: rnd.choice(SLOTS.get(s, [s])) for s in ev["slots"]}
            line = pb.render(v["t"], slots)
            name = f"{eid}-{i:02d}.wav"
            path = os.path.join(by_event, name)
            secs = synth(line, voice, path)
            total_secs += secs
            clips.append(path)
            mark = "*" if v["src"] == "seed" else "~"
            index.append(f"- `{mark}` {line}   — `by-event/{name}` ({secs:.1f}s)")
        if clips:
            allpath = os.path.join(by_event, f"{eid}-all.wav")
            concat(clips, allpath)
            index.append(f"- **all of them in sequence** — `by-event/{eid}-all.wav`")
        index.append("")
        print(f"  {eid}: {len(picks)} clips", file=sys.stderr)

    # The session — the question that actually decides whether this stays on.
    index.append("## session — a plausible hour, in order")
    index.append("")
    clips = []
    for i, (eid, overrides) in enumerate(SESSION, 1):
        ev = bank["events"].get(eid)
        if not ev:
            continue
        v = rnd.choice(ev["variants"])
        slots = {s: overrides.get(s, rnd.choice(SLOTS.get(s, [s]))) for s in ev["slots"]}
        line = pb.render(v["t"], slots)
        voice = AGENT_VOICE if eid in AGENT_EVENTS else SYSTEM_VOICE
        name = f"{i:02d}-{eid}.wav"
        path = os.path.join(session, name)
        secs = synth(line, voice, path)
        total_secs += secs
        clips.append(path)
        mark = "*" if v["src"] == "seed" else "~"
        index.append(f"{i:>2}. `{mark}` {line}   — `session/{name}`")
    if clips:
        secs = concat(clips, os.path.join(session, "00-whole-session.wav"), gap_secs=1.4)
        index.append("")
        index.append(f"**The whole session as one file** — "
                     f"`session/00-whole-session.wav` ({secs:.0f}s)")
    index.append("")
    index.append(f"Total speech staged: {total_secs:.0f} seconds.")

    with open(os.path.join(OUT_DIR, "INDEX.md"), "w") as f:
        f.write("\n".join(index) + "\n")

    print(f"\nstaged in {OUT_DIR}")
    print(f"  {total_secs:.0f}s of speech, nothing played")
    print(f"  read  {os.path.join(OUT_DIR, 'INDEX.md')}")
    print(f"  hear  {os.path.join(OUT_DIR, 'play.sh')}   <- this one makes noise")
    return 0


if __name__ == "__main__":
    sys.exit(main())
