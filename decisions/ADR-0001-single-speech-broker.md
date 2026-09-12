# ADR-0001 — One daemon owns the audio device

**Date:** 2026-09-11 · **Status:** Accepted

## Context
Multiple independent sources need to speak: desktop events, shell results, Claude
Code hooks, manual calls. The existing `omarchy-tts-read-cursor` and
`omarchy-tts-terminal-live` scripts each spawn their own Piper process, so any
two of them active at once produce two voices at once.

## Decision
Exactly one process (`prometheusd`) opens the audio device. Everything else
submits fire-and-forget JSON speech intents to a Unix socket. No other component
is permitted to invoke Piper.

## Consequences
**Good.** Overlap becomes structurally impossible rather than something to
remember to prevent. Priority, dedup, rate limiting, TTL expiry and the
microphone gate all have exactly one place to live. Producers become trivial —
one `jq | socat` line, any language, no library. A warm Piper can be held,
eliminating the measured 0.31 s per-utterance startup.

**Bad.** A single point of failure, and a daemon to keep alive. Mitigated by
`Restart=on-failure` and by making every failure degrade to silence rather than
to a blocked desktop.

## Alternatives rejected
- *Each producer calls Piper directly* — the current design; produces overlap.
- *A lock file* — serializes but can't prioritize, dedup, or preempt.

## Follow-on
The two existing `omarchy-tts-*` scripts should be migrated to route through the
broker (Phase 5.5), so the "one voice" rule holds system-wide rather than only
within Prometheus.
