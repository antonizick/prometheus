# Piper warm-daemon framing — measured

The one genuinely unknown mechanism in Phase 0: how to run Piper as a resident
process and still know where one utterance's audio ends and the next begins.
`--output_raw` emits a headerless PCM stream with no delimiter between
utterances, so this had to be established empirically before `prometheusd`
could be written. Measured 2026-09-11 on `/opt/piper-tts/piper`.

## What Piper actually does

Run with `--json-input --output_raw`, Piper accepts one JSON object per line on
stdin and logs a line per utterance to stderr:

```
[piper] [info] Real-time factor: 0.0568 (infer=0.0712 sec, audio=1.2538 sec)
```

Three findings, each of which changes the design:

**1. `audio=` is cumulative, not per-utterance.** It is the running total of
audio synthesised since the process started. Per-utterance length is the
delta. (`infer=` is cumulative too.)

**2. stdout must be drained concurrently.** Piper writes PCM *before* it logs
the line that describes it. For any utterance larger than the 64 KB pipe
buffer, Piper blocks on the write and the log line never arrives — so waiting
for the marker before reading stdout deadlocks. A dedicated drain thread is
mandatory, not an optimisation.

**3. `--sentence_silence` is excluded from the reported duration.** The default
0.2 s of inter-sentence padding is emitted as audio but not counted in
`audio=`, so the byte count runs ahead of the marker by
`n_sentences × 8820` bytes and the stream desynchronises permanently.

## The protocol

Run with `--sentence_silence 0`, then:

```
bytes_for_this_utterance = round(cumulative_audio × rate) × 2 − bytes_consumed
```

Verified byte-exact (`diff=+0`) across single sentences, multi-sentence input,
and abbreviation edge cases that split unpredictably ("Dr. Smith went to
St. Mary's Ave. today."). Because the padding is gone, the maths holds however
Piper chooses to split — which is what makes it safe for a long-lived daemon.

Inter-sentence pacing is reintroduced by `prometheusd` itself: it splits the
text, synthesises each sentence separately, and inserts its own silence
(`audio.inter_sentence_ms`). This also lowers time-to-first-sound on
multi-sentence utterances and lets a preemption cut cleanly between sentences.

## Measured latency

| | Cold start | Warm |
|---|---|---|
| Model load | 0.233 s | once, at daemon start |
| "Opened Brave browser." | 0.31 s | **0.071 s** |
| 40-word summary | 0.72 s | **0.19 s** |

End-to-end time-to-first-sound through the broker, including spawning paplay:
**48–93 ms**, against the 310 ms cold-start baseline in
[02-system-inventory.md](../docs/02-system-inventory.md).

## Why paplay is not persistent

[01-architecture.md](../docs/01-architecture.md) describes piping into "a
persistent `paplay`". Phase 0 deliberately spawns one paplay per utterance
instead. There is no way to flush a running paplay's buffer, so instant
barge-in — an acceptance criterion — requires killing it. paplay costs ~15 ms
to start against Piper's 233 ms model load, so the warm-process argument that
applies to Piper does not apply here. A shallow `--latency-msec=50` keeps the
unplayed tail short; measured stop latency is **1–19 ms**.
