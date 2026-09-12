# Task 2.4 prep — blind listening comparison

Not played automatically; these are just rendered to file for you to listen to
whenever's convenient. Both candidates came out clean on accuracy and
speakability in the automated benchmark (see `../model-bench.md`), so the
only thing left to decide is how each actually sounds — that's Nick's call,
not something the benchmark script can judge.

`qwen3:4b-instruct` (the current default, 3.2 GB) vs. `qwen3:1.7b` (a
lighter, faster alternative, 1.7 GB) on four of the same real samples:

| Sample | What it's testing |
|---|---|
| `*_git-log` | routine, low-stakes narration |
| `*_test-fail` | reporting a real failure accurately |
| `*_long-168` | compressing a long, nuanced message |
| `*_blocked-q` | the hard case — an agent asking a blocking question (both candidates get this one *wrong*, in different ways; see model-bench.md finding 3 — listen to it anyway, it's informative) |

All rendered with the `agent` voice (`en_GB-alba-medium`, `length_scale
0.7`) — same voice these categories would actually speak in.
