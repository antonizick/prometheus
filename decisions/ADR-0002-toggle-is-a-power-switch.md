# ADR-0002 — The toggle stops processes; it does not set a flag

**Date:** 2026-09-11 · **Status:** Accepted
**Supersedes:** the `OLLAMA_KEEP_ALIVE=-1` approach in the first draft of
[01-architecture.md](../docs/01-architecture.md).

## Context
Requirement from Nick: *"when I have toggled the system off, I am not utilizing
any significant additional overhead… my system continues to be high performing
and snappy."*

The obvious implementation — a daemon that runs always and checks an `enabled`
flag — fails this. Worse, the first draft pinned the summarizer model in VRAM
permanently (`OLLAMA_KEEP_ALIVE=-1`) to avoid load latency. On an 8 GB card that
is 3–5 GB held hostage **whether or not Prometheus is being used**, which would
directly degrade games, video work, and any CUDA task.

## Decision
Three resource states, moved between by starting and stopping systemd units:

- **COLD (off):** zero processes, zero RAM, zero VRAM, zero wakeups. The
  persisted state is a file containing `0`; the keybind is a Hyprland binding
  that launches a script, so nothing of ours needs to be resident for the toggle
  to work.
- **WARM (on, idle):** ~100 MB RAM, ~0 % CPU, **zero VRAM**. Every process blocked
  on a socket read or inotify watch. No polling anywhere.
- **HOT (summarizing):** model loaded on demand, unloaded after
  `OLLAMA_KEEP_ALIVE=5m`.

Ollama is never enabled as an always-on service. `ollama stop` runs on toggle-off
so VRAM is released immediately rather than after a timeout.

## Consequences
**Good.** "Off" is genuinely free and verifiable — `pgrep -af prometheus` returns
nothing and `nvidia-smi` is unchanged. The GPU is free whenever it isn't actively
summarizing. Makes the **pull-based briefing** design fit better: one briefing
loads the model, answers, releases it, versus push narration touching the model
all day.

**Bad.** Toggling on costs a moment of service startup. The first summary after
an idle period pays a 2–4 s model load. Both accepted; the keep-alive duration is
a one-line dial if the balance feels wrong in practice.

## Verification
Acceptance criteria in [04-build-plan.md](../docs/04-build-plan.md) Phase 0, with
`experiments/measure-overhead.sh` recording real numbers. **If warm state exceeds
~150 MB RAM or shows measurable idle CPU, the design is revised** — this is a
gate, not an aspiration.
