# ADR-0004 — Generated variety via an offline phrase bank

**Date:** 2026-09-11 · **Status:** Accepted
**Supersedes:** principle 7 of [06-voice-and-tone.md](../docs/06-voice-and-tone.md)
and the template-only ambient path in [01-architecture.md](../docs/01-architecture.md).

## Context
The original design used fixed templates for recurring events, on the reasoning
that predictable phrasing becomes filterable background noise.

Nick overruled this:

> "ALL of these responses should be 'non-predictable'. This should feel like an
> artificial intelligence, not like I am hearing a script played to me… that
> artificial intelligence illusion should permeate all of the system's responses."

He's right about the failure mode: a system cycling through eleven fixed sentences
stops reading as intelligent almost immediately.

But generating phrasing with an LLM **at event time** is not an option — it would
put a 1–2 s inference in the path of every window focus change and hold 3–5 GB of
VRAM all day, breaking [ADR-0002](ADR-0002-toggle-is-a-power-switch.md).

## Decision
Separate *when the words are written* from *when they are spoken*.

- An **offline authoring pass** uses a large local model to write ~40 distinct
  phrasings per event type, from `persona.md` + `about-me.md`, into
  `phrasebank.json`. Runs occasionally (~30 s, on demand or weekly).
- At **runtime**, ambient narration is a dictionary lookup and a weighted random
  pick excluding the last 15 used. Under 5 ms, zero VRAM.
- Result narration (shell, Claude) already has the LLM in-path, so it gets
  variety from persona injection plus `temperature` 0.7.
- **Structure stays rigid; only wording varies.** Outcome-first, under the word
  cap, no paths or preamble — always.

## Consequences
**Good.** Non-repetitive speech at template speed and template cost. The resource
contract survives intact. The authoring model can be *larger* than the runtime
model since nothing waits on it — personality quality goes up, not down.
Personality becomes editable prose (`persona.md`) rather than code.

**Bad.** A build step and a generated artifact to manage. The bank can drift from
the config if regeneration is forgotten — mitigated by regenerating automatically
when `persona.md`, `about-me.md`, or `register` changes.

**Accepted risk.** Varied phrasing may be *harder* to tune out than fixed
phrasing, since novelty attracts attention. This is the real cost of the
decision. Mitigated by the volume dial (`target_rate`, default 15 %) and a hard
quiet-period floor, rather than by reverting to repetition. Re-evaluate after a
week of real use, using the event journal as evidence.

## Amendment, 2026-09-11 (after building it — task 2.8)

Three things in the decision above survived contact with the hardware, and two
did not. Recorded here rather than quietly changed in the code.

**Survived.** The offline/runtime split, exactly as designed: authoring is
minutes of GPU with nobody waiting, runtime is ~10 µs and loads nothing. The
resource contract is intact. Personality really is editable prose.

**Changed — "~40 distinct phrasings per event type".** Wrong target, and not
because the model is too small. Most moments do not contain forty true things
to say; asked for forty, a model writes the true ones and then invents the
rest. Targets are now per-moment in `phrasebank-spec.json`. The variety the
listener experiences comes from *which moment fires* as much as from the
phrasings within it, and that axis is driven by real context.

**Changed — "uses a large local model to write" (only).** The bank is now
model-written *on top of* eight hand-written seed phrasings per moment, and
everything the model writes must pass a validator that rejects roughly half.
The seeds are a quality floor that does not depend on a regeneration having
gone well, and they double as the few-shot examples. Each phrasing is tagged
`seed` or `model`; the split is inspectable, and `--no-seeds` regenerates
without them to hear the model unaided.

**The reason, stated plainly:** at this hardware's model sizes, generation
quality is not reliable enough to ship unreviewed. `gemma2:9b` beat `qwen3:8b`
clearly (plainer English, far less invention) and is still capable of writing
"Still waiting on the build" about a build that failed. The validator exists
because of that, and the listening review (task 2.10) exists because the
validator cannot hear.

## Related
Nick also asked that every planning-time preference be a config value rather than
a code decision — register, second voice, and which events speak are all dials.
See "Nothing is baked in" in
[08-personality-and-config.md](../docs/08-personality-and-config.md).
