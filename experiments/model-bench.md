# Model bench — Phase 2 task 2.3

Benchmarked against 20 real samples from `samples.jsonl` (task 2.2). Baseline VRAM with nothing loaded: **1059 MiB**. After stopping every candidate: **1084 MiB** — confirms VRAM returns to baseline.

| Model | Role | Load | VRAM | ollama ps | p50 | p95 | tok/s | ≤30 words | clean speakability | NOTHING |
|---|---|---|---|---|---|---|---|---|---|---|
| qwen3:4b-instruct | runtime — primary candidate | 2.98s | 3155 MiB | 3.2 GB | 0.34s | 0.61s | 55.6 | 100.0% | 100.0% | 0/20 |
| llama3.2:3b | runtime — fallback if 4b sluggish | 2.76s | 2563 MiB | 2.6 GB | 0.25s | 0.47s | 69.7 | 95.0% | 95.0% | 0/20 |
| qwen3:1.7b | speed experiment | 2.49s | 1763 MiB | 1.7 GB | 0.19s | 0.38s | 105.8 | 95.0% | 95.0% | 0/20 |
| llama3.2:1b | speed experiment | 2.69s | 1569 MiB | 1.5 GB | 0.13s | 0.51s | 130.0 | 95.0% | 90.0% | 5/20 |
| qwen3:8b | authoring / runtime-quality fallback | 3.08s | 5463 MiB | 5.6 GB | 0.8s | 1.25s | 26.5 | 100.0% | 90.0% | 0/20 |

Raw per-sample responses (all models × all samples) are in `model-bench-raw.jsonl` — that's the input for task 2.4's blind listening test.

**Acceptance targets (docs/04, Phase 2):** p95 < ~2.5s warm, >90% under 30 words, no paths/code/markdown/bullets surviving the post-filter (columns above simulate the filter check, not the actual bin/prometheus-llm post-filter — that always runs regardless of what the model does).

## Findings

**1. The plain `qwen3:4b` tag is now the thinking-only 2507 release — do not use it.**
Confirmed against `ollama list`/the registry (docs/03 flagged exactly this
risk: "exact tags to be confirmed at install time"). It ignores `"think":
false` entirely, on both `/api/generate` and `/api/chat`, and burns the
whole `num_predict` budget on chain-of-thought before ever producing an
answer — the catastrophic failure mode docs/03 warned about under
"deliberately excluded". `qwen3:4b-instruct` is the non-thinking sibling and
is what's now configured. This was caught live: `config.json` still had
`"qwen3:4b"` when `bin/prometheus-llm` was first run end to end, and it
timed out silently exactly as designed — no crash, no garbage output, just
the fail-silent path firing for the wrong reason. Fixed in both
`config/config.json` (template) and the deployed
`~/.config/prometheus/config.json`.

For the two candidates that kept their plain hybrid tag (`qwen3:1.7b`,
`qwen3:8b`), `"think": false` on `/api/chat` genuinely works — verified by
the absence of any `thinking` field or leaked `<think>` content across all
20 samples for both. `bin/prometheus-llm` sends `"think": false`
unconditionally; it's a harmless no-op on non-hybrid tags like
`qwen3:4b-instruct` (confirmed directly).

**2. The prompt's own negative example gets echoed back as a hallucinated fact — worse on smaller models.**
The instructions block includes: `Say "the auth middleware", not
"src/auth/mw.ts"` — a concrete, plausible-sounding example. Weaker models
latch onto it and report it as if it were the actual outcome, regardless of
what the sample actually said:

| Model | Responses mentioning "auth middleware" | Severity |
|---|---|---|
| qwen3:4b-instruct | 0/20 | — |
| qwen3:8b | 0/20 | — |
| qwen3:1.7b | 3/20 (15%) | Mild — plausible-sounding filler tacked onto an otherwise correct reply |
| llama3.2:3b | 4/20 (20%) | Real — fabricates a wrong outcome, e.g. reports `test-run-failure` as *"Authentication middleware returned an error message"* when the actual failure was an unrelated missing-menu-item assertion |
| llama3.2:1b | 8/20 (40%) | Severe — degenerates into a repetition loop on `claude-long-132` (`"Auth middleware, not src/auth/mw.js. The auth middleware, not the src/auth/mw.js. No, the auth middl…"`), and silently drops a real command failure (`python-traceback`, a `FileNotFoundError`) by replying `NOTHING` |

This directly violates the "pass/fail outcomes never reported backwards"
acceptance criterion for `llama3.2:3b` and disqualifies `llama3.2:1b`
outright — it is not a safe fallback as currently prompted, despite docs/03
listing it as one. **Recommendation:** before leaning on either `llama3.2`
size, replace the negative example with something less copyable (a nonsense
placeholder rather than a plausible file path), then re-run this benchmark.
Until then, treat `qwen3:1.7b` — not `llama3.2:3b` — as the real fallback if
`qwen3:4b-instruct` ever needs a lighter alternative: same family, no
observed hallucination worse than mild filler, and still comfortably faster
(1.7 GB, p95 0.38s vs. 4b-instruct's 3.2 GB, p95 0.61s).

**3. Every candidate mishandles a genuinely hard sample: an agent asking a blocking question.**
`claude-blocked-question` (real Claude message: *"Could you run this one
too so I can see the actual error? ... sudo modprobe omen_rgb_keyboard..."*)
is exactly the content about-me.md calls "the single most valuable alert."
All five candidates got it wrong, in two different ways:

- `qwen3:4b-instruct` and `qwen3:8b` **hallucinated a completed outcome**
  ("Modprobe loaded... no errors") — nothing has actually happened yet, the
  message is a live question.
- `llama3.2:3b` and `qwen3:1.7b` **suppressed it entirely** via the
  `NOTHING` escape hatch — silencing the one thing Nick most wants to hear.

This isn't a Phase 2 blocker: per docs/03's own routing table, a blocked
agent's `Notification` hook is meant to go through the dedicated
`claude_blocked` / `critical`-priority phrase-bank path (Phase 3, task 3.2),
not this general-purpose narrator prompt. But it's worth flagging now
because the failure mode is exactly backwards from what the design intends,
and it should inform Phase 3's prompt/routing rather than be rediscovered
there.

**4. Everything comfortably beats the latency budget.**
Even the largest candidate (`qwen3:8b`, 8x the parameters of the smallest)
posts p95 1.25s against the 2.5s warm-latency target, and every candidate's
`num_predict=60` cap turned out to rarely bind — models mostly self-limited
to 1-2 short sentences on their own. Load time is consistently ~2.5-3.1s
regardless of model size in this range, which matches docs/03's estimate and
is the real cost of the keep-alive design: paid once per burst of activity,
not once per summary.

**Recommendation for task 2.4 (Nick's blind listening test):** compare
`qwen3:4b-instruct` against `qwen3:1.7b` specifically — both are clean on
accuracy and hallucination, so the deciding factor is genuinely how each
*sounds*, which is exactly point 7 of the benchmark protocol and not
something this script can judge. `model-bench-raw.jsonl` has all 100
responses (5 models × 20 samples) ready to synthesize and compare.
