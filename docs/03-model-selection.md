# 03 — Model Selection

Where AI is used, where it deliberately isn't, and which specific models to run.

---

## First: most of this system uses no AI at all

Worth stating up front, because the instinct is to route everything through a
model, and that instinct is wrong here.

| Job | Approach | Why |
|---|---|---|
| "Brave." on window open | **Pre-generated phrase bank** | Must be < 300 ms with zero VRAM. Wording is LLM-written, just *offline* — variety without latency. |
| "Workspace three." | **Phrase bank** | Same. |
| "Build failed. Exit code one." | **Phrase bank + exit code** | Outcome is already structured data; only the wording needs variety. |
| Short Claude reply (< 25 words) | **Speak it, lightly cleaned** | Faithful and instant. Summarizing something already short adds risk and latency for nothing. |
| Long Claude reply → 2 sentences | **Local LLM** | Genuine compression task. |
| Command output → 2 sentences | **Local LLM** | Genuine compression task. |
| Multi-event briefing | **Local LLM** | Genuine synthesis task. |

| Phrase-bank authoring | **Local LLM, offline batch** | Not latency-bound — can use a *bigger* model. |

**No path calls a model at event time unless it genuinely must.** This is what
keeps the system snappy and the GPU free (see
[07-resource-profile.md](07-resource-profile.md)). The LLM does two jobs:
compressing long text on demand, and writing the phrase bank ahead of time.

---

## Two models, two very different jobs

This split falls out of the variety requirement
([08](08-personality-and-config.md)) and is one of the better consequences of it.

### Runtime summarizer — *latency-bound*
Runs while Nick is waiting. Must answer in ~1–2 s or be cancelled. Small model.

### Phrase-bank author — *quality-bound*
Runs offline, occasionally, when nobody is waiting. Writes ~40 distinct phrasings
per event type from `persona.md` + `about-me.md`. Taking 30 seconds is completely
fine, and this is where the system's personality actually comes from — so it
should use **the best model that fits in VRAM**, not the fastest.

Spending 5 GB and half a minute once a week to get better writing, then running
free lookups all week, is a far better trade than a small model improvising at
every event.

---

## Runtime: Ollama

`extra/ollama-cuda 0.33.3-1` — official Arch repo, CUDA build, no AUR.

Chosen over llama.cpp directly, LM Studio, or vLLM because it's packaged for this
distro, has a stable local HTTP API, handles model loading/unloading and the
keep-alive timer natively, and makes swapping models a one-word config change —
which matters a lot while tuning.

**Not** enabled as an always-on system service. It starts and stops with
Prometheus, per [07](07-resource-profile.md).

---

## Hardware budget

RTX 2070 Max-Q, **8 GB VRAM**. Comfortable room, but not unlimited — and the
requirement that the GPU be free when idle means we should prefer the *smallest
model that does the job well*, not the largest that fits.

| Class | Q4 VRAM | Load time | Tok/s (est.) | 30-word summary |
|---|---|---|---|---|
| 1–2 B | ~1–1.5 GB | < 1 s | 100–150 | < 1 s |
| **3–4 B** | **~2.5–3 GB** | **~1–2 s** | **60–100** | **~1 s** |
| 7–8 B | ~4.5–5.5 GB | ~2–4 s | 35–50 | ~1.5–2 s |
| 13 B+ | 8 GB+ | slow | 15–25 | too slow |

Estimates from the hardware class, to be replaced with measurements in Phase 2.

---

## The task is easier than it looks

The summarization job here is narrow, and that's why a small model is the right
call rather than a compromise:

- Input is short (a command's output tail, or one assistant message)
- Output is tiny (two sentences, ~25 words)
- No reasoning, no tool use, no multi-turn, no world knowledge
- Failure is cheap — a mediocre sentence, not a wrong action

This is well within 3B-class capability. The failure mode to actually worry about
is not *stupidity* — it's **verbosity**: small models love to write "Here's a
summary of the output:" and then a bulleted list. That's a prompting and
`num_predict` problem, and it's solved the same way regardless of model size.

---

## Candidates — benchmarked and confirmed in Phase 2

Benchmarked head-to-head in Phase 2 on 20 real samples from this machine
(`experiments/model-bench.md`), then the winner confirmed **by ear** against
the runner-up (task 2.4) — text that reads fine frequently sounds wrong, and
here it didn't: the by-ear result matched the benchmark.

### Runtime summarizer — `qwen3:4b-instruct` ✅ **confirmed, in use**
Not the bare `qwen3:4b` tag — see the tag-resolution note below. Best
quality-per-VRAM in this class, zero hallucinated outcomes over 20 samples,
and won the blind listening test outright. ~3.2 GB, p50 0.34 s / p95 0.61 s
warm, loads in ~3 s cold.

### Phrase-bank author — `gemma2:9b` ✅ **confirmed by head-to-head, in use**
**Not `qwen3:8b`**, which this document named before the job existed to test
it against. On the real authoring prompt, `qwen3:8b` writes in a register
nobody speaks in and invents heavily — "Brave's tabs still wait", "Brave's
place waits unoccupied" — and collapses into one sentence repeated with the
last word swapped ("{app} active. / {app} ready. / {app} loaded.") within ten
lines. `gemma2:9b` writes plain spoken English on the same prompt.

Measured through the phrase-bank validator on the same event: **43 % of
`gemma2:9b`'s candidates survived, against 18 % of `qwen3:8b`'s.** ~5.4 GB,
fits with headroom alongside nothing else, ~27 tok/s on this card, released
by the same keep-alive as everything else. `qwen3:8b` stays configured as
`authoring_fallback_model`.

Two prompt findings that came out of that comparison and matter more than the
model choice:

1. **Generate against a real value, not a placeholder.** Asked to write about
   `{app}`, both models degenerate immediately; asked to write about "Brave",
   they write English. The value is turned back into a placeholder afterwards.
2. **A single user message, no system role.** gemma2's chat template has no
   system turn, and splitting instructions across roles visibly weakened
   constraint-following — it stopped honouring "mention the app exactly once".

A 14B quantized would not fit alongside the ~1.2 GB the desktop already holds,
so the 9B class is the ceiling here for now.

### Fallback if resource pressure forces a downgrade — `qwen3:1.7b` ✅ **confirmed**
**Not `llama3.2:3b`.** Benchmarking found `llama3.2:3b` hallucinates a wrong
pass/fail outcome 4/20 times (see "deliberately excluded" note below) — it
is disqualified as a fallback until that's fixed, regardless of its
speed. `qwen3:1.7b` is the real fallback: same family as the primary choice,
only mild hallucination (3/20, never a wrong outcome, just tacked-on
filler), 1.7 GB instead of 3.2 GB, and still comfortably under the latency
budget (p95 0.38 s). Confirmed by ear as acceptable, just a step down from
`4b-instruct`. Use this if VRAM or GPU contention ever forces a lighter
runtime model.

### Ruled out — `llama3.2:3b`, `llama3.2:1b`
Both hallucinate the prompt's own negative example
(`"the auth middleware", not "src/auth/mw.ts"`) back as a real outcome —
`3b` 4/20 times, `1b` 8/20 times including one degenerate repetition loop
and one real crash traceback silently dropped. See model-bench.md finding 2
for the full breakdown and a note on fixing the prompt's example wording,
which might rehabilitate this family later.

### The tag-resolution trap, confirmed live
Qwen's 2507 refresh split the 4B size into separate `-instruct` and
`-thinking` releases; the bare `qwen3:4b` tag now resolves to
thinking-only, ignores `"think": false` on both `/api/generate` and
`/api/chat`, and spends its entire `num_predict` budget on chain-of-thought
before answering — exactly the failure mode "deliberately excluded" below
warns about. `qwen3:1.7b` and `qwen3:8b` kept their original hybrid tags and
do honor `"think": false` correctly. `bin/prometheus-llm` sends
`"think": false` unconditionally on every call — verified harmless on
non-hybrid tags like `qwen3:4b-instruct`. Moral, confirmed rather than just
anticipated: **always re-check exact tags against `ollama list` /
the registry at install time, per-size, not just once.**

### Deliberately excluded
- **Reasoning / thinking models** — they emit long chains of thought before
  answering. Catastrophic for a latency-sensitive task. If a Qwen3 variant with
  thinking is used, thinking must be disabled.
- **Cloud APIs** — the stated constraint is low/no cost; this task never needs
  frontier capability.
- **Anything over 8B** — too slow, too much VRAM, no quality benefit here.

---

## Benchmark protocol (Phase 2)

Assemble ~20 real samples from this machine: build output, test runs, `git`
output, long error traces, and real Claude Code assistant messages. Then for each
candidate record:

1. **Load time** (cold → ready)
2. **Latency** per summary, p50 and p95
3. **VRAM** actually used
4. **Length discipline** — % of outputs over 30 words *(the most common failure)*
5. **Speakability** — does it emit paths, code, lists, markdown?
6. **Accuracy** — does it get the outcome right? Especially pass/fail.
7. **Blind quality ranking** by Nick, listening to the Piper output rather than
   reading the text

Point 7 is the deciding one. This output is *heard*, never read, and text that
looks fine can sound terrible. Results → `experiments/model-bench.md`.

---

## Prompting

The prompt does more work than the model choice. The persona and user-context
files ([08](08-personality-and-config.md)) are prepended to every prompt below,
which is what makes the output sound like a specific system rather than a generic
summarizer.

Constraints, enforced:

```
{persona.md}
{about-me.md}

You narrate a developer's computer out loud. You will be given the output
of a command or an AI assistant's message.

Reply with at most two short sentences describing the outcome, written to be
spoken aloud.

Never use: lists, bullet points, markdown, file paths, function names,
code, or identifiers. Say "the auth middleware", not "src/auth/mw.ts".
Never begin with "Here is" or "The output shows". State the outcome directly.
If nothing noteworthy happened, reply exactly: NOTHING
```

- `num_predict` hard cap (~60 tokens) so length is enforced mechanically, not by
  hoping the model complies.
- `temperature` ~0.7 — higher than a pure factual task would want, because
  non-repetitiveness is an explicit requirement. Accuracy is protected by the
  post-filter and by the fact that pass/fail is passed in as structured data
  rather than inferred. If outcomes ever get reported backwards, this is the
  first dial to lower.
- The **`NOTHING` escape hatch is important**: it gives the model an explicit way
  to say "not worth speaking," which is the behavior we most want to encourage.
  Any response containing `NOTHING` is silently dropped.
- Post-filter regardless: strip markdown, drop anything path-like, truncate at
  the word limit. Never trust the model to have obeyed.

---

## Speech-to-text (for completeness)

Already solved. Voxtype with Whisper `base.en`. Not in scope, not being changed.

If dictation accuracy ever needs improving, `small.en` or `large-v3-turbo` would
be the step up — this machine could run either. Noted only so it's on record; no
change is proposed.
