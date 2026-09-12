# 09 — Session and Budget Plan

How to run the build across multiple Claude Code sessions without burning tokens.

**The core problem:** the planning docs total **~20,000 tokens**. Reading all of
them at the start of every session is pure waste — each session needs two or
three, not fourteen. This document says exactly which ones, and which model to
use for each phase.

---

## Relative model cost

| Model | Input $/MTok | Output $/MTok | Relative to Opus |
|---|---|---|---|
| **Opus 5** | $5.00 | $25.00 | 1× |
| **Sonnet 5** | $2.00 | $10.00 | **0.4× — 2.5× cheaper** |
| **Haiku 4.5** | $1.00 | $5.00 | 0.2× — 5× cheaper |

*(First-party API rates as of 2026-06-24. On a subscription plan the dollar
figures don't bill directly, but the ratios still govern how fast usage limits
are consumed — Opus drains ~2.5× faster than Sonnet for the same work.)*

**The general rule for this project:** design and taste work is worth Opus;
implementing an already-written spec is Sonnet's job. Most of this build is the
second kind — the planning is done, which is precisely what makes cheaper models
viable for the implementation.

---

## Phase → model map

| Phase | Model | Why |
|---|---|---|
| **0 — Foundation** | **Opus 5** | Concurrent daemon, subprocess lifecycle, queue preemption, systemd. Fiddly, and every later phase sits on top of it. Worth paying for once. |
| **1 — Journal + briefing** | **Sonnet 5** | Socket parsing, JSONL, filtering, scoring weights. Fully specified, mechanical. |
| **2a — Ollama + benchmarks** | **Sonnet 5** | Install, wire the API, run a benchmark harness. Rote work. |
| **2b — Phrase bank + persona** | **Opus 5** | Prompt authoring and phrasing quality. This *is* the personality — the one place taste pays. |
| **3 — Claude Code hooks** | **Sonnet 5** | Well-scoped. Use the `claude-code-guide` agent for hook schema questions instead of guessing. |
| **4 — Shell integration** | **Sonnet 5** | Bash hooks and a wrapper script. Straightforward. |
| **5 — Tuning and taste** | **Opus 5** | Judgment about what sounds right. Not mechanizable. |

**Rough split: two or three Opus sessions, four Sonnet sessions.** If the budget
gets tight, Phase 0 on Sonnet is workable — the design is detailed enough — but
I'd protect 2b and 5, since those are the difference between a system that works
and one you keep switched on.

Switch models with `/model sonnet` or `/model opus` at the start of a session.
`/fast` toggles faster Opus output when you want it.

---

## What to read in each session

Never say "read the docs." Name the files. Each session should load **4–8k
tokens** of planning, not 20k.

| Session | Read these | ~Tokens |
|---|---|---|
| Phase 0 | `01-architecture.md`, `07-resource-profile.md`, `02-system-inventory.md` | ~6.1k |
| Phase 1 | `01-architecture.md`, `08-personality-and-config.md` (attention section) | ~6.3k |
| Phase 2a | `03-model-selection.md`, `07-resource-profile.md` | ~3.5k |
| Phase 2b | `08-personality-and-config.md`, `06-voice-and-tone.md` | ~4.5k |
| Phase 3 | `01-architecture.md` (claude section), `04-build-plan.md` Phase 3 | ~5.4k |
| Phase 4 | `01-architecture.md` (shell section), `05-risks…` Q2 | ~4.9k |
| Phase 5 | `06-voice-and-tone.md`, `08-personality-and-config.md`, `07-resource-profile.md` | ~6.1k |

`00-feasibility.md` never needs re-reading — it's the record of *why* we started,
not how to build. Same for the ADRs unless a decision is being revisited.

---

## Compact vs. clear

| | When | Cost |
|---|---|---|
| **`/clear`** | **At every phase boundary, always.** | Free. Needs a restart prompt (below). |
| **`/compact`** | Mid-phase, context filling, work unfinished | One summarization call. Keeps continuity. |
| Neither | Context under ~50 % and work flowing | — |

**Rule of thumb: clear *between* phases, compact *within* them.**

A phase boundary is a natural clean break — the work is committed, the docs are
updated, and nothing in the old context is needed. Carrying it forward just makes
every subsequent turn more expensive, since context is resent on each one.

### What I'll watch for, and tell you proactively

I'll flag it when:

- **A phase completes** → "Phase N done. `/clear` and start Phase N+1 with
  `/model <x>`, prompt below."
- **Context passes ~60 %** mid-phase → I'll suggest `/compact` and say what to
  preserve.
- **A long debugging loop** has filled context with failed attempts and stale
  tool output → `/compact` is usually better than continuing.
- **We've drifted off-phase** → better to clear and restart scoped than to keep
  a muddled context.
- **A session is doing mechanical work on Opus** → I'll say so, so you can drop
  to Sonnet.

I'll say these unprompted. You shouldn't have to track it.

---

## Restart prompts

Copy-paste after `/clear`. Each one sets the model, names the docs, and scopes the
work — so the session starts productive instead of re-deriving context.

### Phase 0 — Foundation · `/model opus`
```
We're building Prometheus, a conversational voice layer for Omarchy.
Project root: ~/Work/prometheus

Read these first:
  docs/01-architecture.md
  docs/07-resource-profile.md
  docs/02-system-inventory.md

Build Phase 0 from docs/04-build-plan.md (tasks 0.1–0.10): the prometheusd
speech broker, warm Piper, sticky toggle, config files, systemd units, keybinds,
and the overhead measurement script.

Hard constraints: the Piper voice settings are locked (en_GB-alan-medium,
length_scale 0.7). Toggled off must mean zero processes and zero VRAM. No
polling anywhere. Meet the Phase 0 acceptance criteria in the build plan.
```

### Phase 1 — Journal + briefing · `/model sonnet`
```
Continuing Prometheus at ~/Work/prometheus. Phase 0 (speech broker + toggle)
is built and working.

Read docs/01-architecture.md and the "selective attention" section of
docs/08-personality-and-config.md.

Build Phase 1 from docs/04-build-plan.md (tasks 1.1–1.8): Hyprland event
listener, the JSONL event journal, app-name mapping, event filtering, interest
scoring, `prometheus brief`, and the replay harness.

Critical: filter out windowtitle churn — animated spinners in window titles will
otherwise spam the journal several times a second. No narration yet in this
phase; we're collecting data first.
```

### Phase 2a — Ollama + benchmarks · `/model sonnet`
```
Continuing Prometheus at ~/Work/prometheus. Phases 0–1 done.

Read docs/03-model-selection.md and docs/07-resource-profile.md.

Build Phase 2 tasks 2.1–2.6 from docs/04-build-plan.md: install ollama-cuda,
assemble ~20 real output samples from this machine, benchmark the candidate
models on latency / VRAM / length discipline / speakability, and build the
prometheus-llm wrapper.

Do NOT enable ollama as an always-on service, and do NOT set
OLLAMA_KEEP_ALIVE=-1. Verify VRAM is released after the keep-alive window —
that's an acceptance criterion.
```

### Phase 2b — Phrase bank + persona · `/model opus`
```
Continuing Prometheus at ~/Work/prometheus. Ollama is installed and benchmarked.

Read docs/08-personality-and-config.md and docs/06-voice-and-tone.md.

Build tasks 2.8–2.10: `prometheus regenerate` (offline phrase-bank authoring
from persona.md + about-me.md), runtime bank selection with avoid_last_n, and
write the first real persona.md and about-me.md.

This is the phase that decides whether the system sounds like intelligence or
like a script. Generate a full bank, synthesize a representative sample through
Piper, and let me listen to it before anything goes live.
```

### Phase 3 — Claude Code hooks · `/model sonnet`
```
Continuing Prometheus at ~/Work/prometheus. Phases 0–2 done.

Read the "prometheus-claude" section of docs/01-architecture.md and Phase 3 of
docs/04-build-plan.md.

Build Phase 3: Claude Code hooks for Stop and Notification, transcript reading,
the short-message short-circuit, and markdown/path stripping.

Start with task 3.1 — log the raw hook payloads and verify the actual schema
before building anything on top of it. Use the claude-code-guide agent for hook
questions rather than guessing. Hooks must never block or slow a Claude turn.
```

### Phase 4 — Shell integration · `/model sonnet`
```
Continuing Prometheus at ~/Work/prometheus. Phases 0–3 done.

Read the "prometheus-shell" section of docs/01-architecture.md and Q2 in
docs/05-risks-and-open-questions.md.

Build Phase 4: PROMPT_COMMAND hook for command + exit code + duration,
exit-code narration for long or failed commands only, and the opt-in `pr`
wrapper that captures output and routes it to the summarizer.

Fast successful commands must produce silence. Shell prompt latency must not
increase measurably.
```

### Phase 5 — Tuning and taste · `/model opus`
```
Continuing Prometheus at ~/Work/prometheus. All phases built; now living with it.

Read docs/06-voice-and-tone.md, docs/08-personality-and-config.md, and
docs/07-resource-profile.md.

Phase 5 work: tune interest scoring against real journal data, build the
verbosity profiles, run a voice-and-tone pass (synthesized and listened to, not
read), add context gates (screen locked, fullscreen, other audio), migrate the
old omarchy-tts-* scripts to route through the broker, and re-measure overhead.

Use the replay harness against real journalled history to see what would have
been spoken before changing any weights.
```

---

## Token discipline while working

Things that quietly burn budget, in rough order of impact:

1. **Re-reading large files you've already read.** The harness tracks file state
   — a re-read to "verify" an edit that already succeeded is wasted.
2. **Dumping long command output into context.** Pipe through `head`, `grep`, or
   `wc` rather than printing a 6 MB log. (`~/.config/hypr/hyprland.log` is
   already 6.6 MB.)
3. **Subagents.** Each one starts cold and re-derives context. Useful for genuine
   wide searches; expensive for anything a direct tool call answers.
4. **Long debugging loops.** Five failed attempts in context make every later turn
   more expensive. Compact and restate the problem.
5. **Reading all fourteen planning docs.** Use the table above.

Prompt caching means a stable prefix is cheap to resend — so a session that reads
its three docs *once at the start* and then works is far cheaper than one that
reads files scattered throughout.

---

## Where to record progress

At the end of each session, append to `notes/YYYY-MM-DD-phase-N.md`: what got
built, what's verified, what's broken, what's next. Keep it under ~300 words.

That note is what makes the next `/clear` safe — it's the handoff, and it costs
a few hundred tokens to read instead of reconstructing state by exploring the
repo. Mention it in the restart prompt if a phase ended mid-work:

> `Read notes/2026-09-14-phase-0.md for where we left off.`
