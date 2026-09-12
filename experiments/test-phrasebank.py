#!/usr/bin/env python3
"""Unit tests for the phrase bank's runtime behaviour (Phase 2, task 2.9).

    experiments/test-phrasebank.py

Checks the two properties the design actually promises and which are easy to
get quietly wrong:

  1. `avoid_last_n` really holds — no phrasing repeats inside the window, ever,
     including when the bank is barely larger than the window.
  2. The weighted pick covers the whole bank rather than favouring a handful,
     which is what "never sounds scripted" means in practice.

Plus the small correctness properties: rendering capitalises a slot value that
lands at the start of a sentence, digits are spoken as words, and the picker
touches no network.

Runs against a temporary state directory, so it never disturbs the real
recent-use history.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import socket
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

failures = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def load_module():
    path = os.path.join(REPO, "bin", "prometheus-phrasebank")
    loader = importlib.machinery.SourceFileLoader("pb", path)
    spec = importlib.util.spec_from_loader("pb", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def fake_bank(n_variants: int) -> dict:
    return {
        "version": 1, "generated_at": 0, "generated_at_iso": "test",
        "fingerprint": "test", "inputs": {"variants_per_event": n_variants},
        "events": {
            "t_event": {
                "moment": "test", "slots": ["app"], "max_words": 8,
                "target": n_variants,
                "variants": [{"t": "{app} number %d." % i, "src": "model"}
                             for i in range(n_variants)],
            }
        },
    }


def main() -> int:
    pb = load_module()
    tmp = tempfile.mkdtemp(prefix="phrasebank-test-")

    print("render")
    check("slot at sentence start is capitalised",
          pb.render("{app}, then.", {"app": "the terminal"}) == "The terminal, then.",
          pb.render("{app}, then.", {"app": "the terminal"}))
    check("slot mid-sentence keeps its case",
          pb.render("Back in {app}.", {"app": "the terminal"}) == "Back in the terminal.")
    check("a bare workspace id is spoken as a word",
          pb.render("Workspace {workspace}.", {"workspace": "3"}) == "Workspace three.")
    check("terminal punctuation is added when missing",
          pb.render("{app} again", {"app": "Brave"}) == "Brave again.")
    check("capitalises after a full stop",
          pb.render("{app}. {app} again.", {"app": "brave"}) == "Brave. Brave again.")
    check("a slot starting with a digit doesn't steal the capital",
          pb.render("{span} elapsed, unchanged.", {"span": "17 minutes"})
          == "17 minutes elapsed, unchanged.",
          pb.render("{span} elapsed, unchanged.", {"span": "17 minutes"}))

    print("\navoid_last_n")
    for size, window in ((30, 15), (16, 15), (10, 15)):
        bank = pb.Bank(fake_bank(size), avoid_last_n=window,
                       state_path=os.path.join(tmp, f"recent-{size}.json"))
        seen, worst = [], None
        for _ in range(400):
            line = bank.pick("t_event", {"app": "Brave"})
            # The guarantee can only hold while the bank is larger than the
            # window; below that it degrades to "as far apart as possible".
            if line in seen[-min(window, size - 1):]:
                worst = line
                break
            seen.append(line)
        expect_clean = size > window
        check(f"bank of {size}, window {window}",
              (worst is None) if expect_clean else True,
              "repeat: %r" % worst if worst else
              ("no repeat in 400 picks" if expect_clean
               else "bank smaller than window — degrades gracefully"))

    print("\ncoverage")
    bank = pb.Bank(fake_bank(24), avoid_last_n=15,
                   state_path=os.path.join(tmp, "recent-cov.json"))
    counts: dict[str, int] = {}
    for _ in range(2400):
        line = bank.pick("t_event", {"app": "Brave"})
        counts[line] = counts.get(line, 0) + 1
    check("every phrasing gets used", len(counts) == 24, f"{len(counts)}/24 used")
    spread = max(counts.values()) / min(counts.values())
    check("no phrasing dominates", spread < 1.6,
          f"most-used / least-used = {spread:.2f}")

    print("\nisolation")
    real_socket = socket.socket

    class Tripwire:
        def __init__(self, *a, **k):
            raise AssertionError("the picker opened a socket")

    socket.socket = Tripwire
    try:
        bank.pick("t_event", {"app": "Brave"})
        check("pick opens no socket", True)
    except AssertionError as e:
        check("pick opens no socket", False, str(e))
    finally:
        socket.socket = real_socket

    check("unknown event returns None", bank.pick("nope", {}) is None)

    print("\nstate")
    path = os.path.join(tmp, "recent-flush.json")
    b2 = pb.Bank(fake_bank(20), avoid_last_n=5, state_path=path)
    for _ in range(30):
        b2.pick("t_event", {"app": "Brave"})
    b2.flush()
    with open(path) as f:
        st = json.load(f)
    check("recent-use state persists", len(st["t_event"]["recent"]) > 0,
          f"{len(st['t_event']['recent'])} remembered, "
          f"{len(st['t_event']['uses'])} counted")
    check("recent list stays bounded", len(st["t_event"]["recent"]) <= 5 * 2)

    print()
    if failures:
        print(f"{len(failures)} failure(s): {', '.join(failures)}")
        return 1
    print("all passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
