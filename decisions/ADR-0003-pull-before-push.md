# ADR-0003 — Pull before push

**Date:** 2026-09-11 · **Status:** Accepted (recommendation — Nick's call, see Q1)

## Context
The original framing was push-based: the OS comments on things as they happen.
That's the intuitive design, and it has a hard ceiling — every utterance is an
interruption you didn't ask for. The annoyance budget gets spent on low-value
events and the system gets switched off permanently. The existing "read every
line of terminal output" mode already shows this failure shape.

## Decision
Split narration by whether it can wait.

- **Push** — only what can't: *an agent is blocked waiting on you*; *a long
  command failed*. That's close to the whole list.
- **Pull** — everything else, via `prometheus brief` on `SUPER + SHIFT + B`,
  summarizing what's happened since the last briefing.

An append-only event journal (`~/.local/state/prometheus/journal`) records
everything the daemon observes, spoken or not, and is what the briefing reads.

## Consequences
**Good.** Inverts the economics: silence plus a five-second summary when *you*
have attention to spend, instead of twenty interruptions of which two mattered.
Batched summarization is a task small models do well, and it runs once per
request rather than once per event — which fits on-demand model loading
(see [ADR-0002](ADR-0002-toggle-is-a-power-switch.md)) precisely. The journal
also becomes the evidence base for deciding what *should* be pushed.

**Bad.** Requires remembering to press a key. Some value from ambient awareness is
lost. Mitigated by keeping the genuinely urgent cases on the push path.

## Note on sequencing
This is why [04-build-plan.md](../docs/04-build-plan.md) builds the journal and
briefing (Phase 1) before any narration. A few days of journal data is much
better evidence for what deserves to be spoken than deciding now.
