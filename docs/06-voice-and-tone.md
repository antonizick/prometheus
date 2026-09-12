# 06 — Voice and Tone

The quality bar for this project is not "does it speak" — that's Phase 0 and it's
easy. It's **"is it still on after a week."** That's decided here.

---

## The governing constraint

**Piper at `length_scale 0.7` speaks about 4 words per second.**

Measured, not estimated: a 40-word summary is a **ten-second** monologue. Ten
seconds is an extremely long time to be talked at when you didn't ask a question.

| Words | Spoken time | Feels like |
|---|---|---|
| 3 | 0.7 s | A notification sound |
| 10 | 2.5 s | A colleague's aside |
| 25 | 6 s | A statement |
| 40 | 10 s | **Too long** |
| 100 | 25 s | Unbearable |

**Target: under 15 words for anything unprompted.** The briefing can run longer
because you asked for it.

This single number should drive every phrasing decision.

---

## Principles

**1. Silence is the default.** The system's most common output is nothing. Every
utterance has to earn its place against the alternative of staying quiet.

**2. Lead with the outcome.** You may stop listening after four words, so the
first four must carry the point.

> ✅ "Build failed. Two errors in the parser."
> ❌ "I've finished running the build you started, and it looks like there were
>    some errors."

**3. Never speak what can't be heard.** Paths, identifiers, code, version strings
and hashes are visual objects. Spoken aloud they're noise.

> ✅ "Changed the auth middleware."
> ❌ "Modified src/auth/middleware.ts line 47."

**4. No preamble.** "Here's a summary of..." — never. Start with the fact.

**5. Numbers only when they change a decision.** "Two errors" is worth saying.
"Compiled in 4.7 seconds" is not.

**6. Don't narrate the obvious.** If Nick just pressed enter on a build, he knows
a build started. Say what he *couldn't* know — how it ended.

**7. ~~Absolute consistency for recurring events.~~ → Constant structure, never
the same words.** *(Revised 2026-09-11 at Nick's direction —
see [08-personality-and-config.md](08-personality-and-config.md) and
[ADR-0004](../decisions/ADR-0004-generated-variety.md).)*

The original principle here said the same event should always produce the same
sentence, because predictability makes speech filterable as background. Nick
overruled it, and the reasoning is sound: a system that cycles through eleven
fixed sentences stops feeling like intelligence almost immediately, and that
matters more to him than filterability.

So the rule becomes: **the shape is rigid, the words never repeat.**

- Always outcome-first, always under the word cap, never any paths or preamble —
  so you know what kind of thing you're hearing within one word.
- Never the same sentence twice — phrasings come from a generated bank of ~40
  variants per event, refreshed periodically.

The consistency that mattered was structural, not lexical. A colleague saying
"build's broken" one day and "that build didn't make it" the next is no harder to
parse — the information arrives in the same place either way.

---

## Register — a config dial, not a fixed decision

| Register | Example |
|---|---|
| Terse | "Build failed. Two errors." |
| **Neutral** *(default)* | "The build failed with two errors in the parser." |
| Warm | "Build's unhappy — a couple of errors in the parser." |

This is `config.json` → `register`. Change the word, run
`prometheus regenerate`, and the whole phrase bank is rewritten in the new voice
in about thirty seconds. It is not a decision that needs to be right now.

My recommendation remains **neutral, trending terse** — warm is delightful for
ten minutes and can grate by day three, and personality in something that speaks
unprompted twenty times a day risks becoming a tic. But this is precisely the
kind of thing that can only be judged by living with it, which is why it's a dial.

The failure mode to avoid at any register is a computer with a *mood*. "Uh oh,
looks like something went wrong!" is unbearable the fourth time — and that's a
constraint in `persona.md`, enforced across all three registers.

---

## Draft phrasebook

These are **seed examples**, not the final script — they show the target shape
and length for each event type, and the generated bank of ~40 variants per event
is written to match. Every one is a proposal to be **listened to before
adoption**, not approved on the page.

### Ambient — from the phrase bank, ~15 % of events
| Event | Says |
|---|---|
| App opened | "Brave." |
| App closed | *(nothing — closing is intentional and known)* |
| Workspace switched | "Three." |
| Fullscreen | *(nothing)* |
| Display connected | "Second display on." |

Note how short these are. The app's name alone is the entire message. "You have
opened the Brave browser" says nothing more and takes six times as long.

### Shell
| Situation | Says |
|---|---|
| Fast success (< 10 s) | *(nothing)* |
| Long success | "Build done. Forty seconds." |
| Failure | "Build failed. Exit one." |
| Summarized (`pr`) | "All forty-seven tests passed." |
| Summarized failure | "Three tests failed, all in the parser." |

### Claude Code
| Situation | Says |
|---|---|
| **Waiting for input** | **"Claude needs you."** |
| Waiting, with project | "Claude needs you — prometheus." |
| Finished, short reply | *(the reply itself, cleaned)* |
| Finished, long reply | "Rewrote the auth middleware. Tests pass." |
| Session ended | *(nothing)* |

"Claude needs you" is three words and half a second, and it's plausibly the most
valuable thing this entire system will ever say.

### System
| Event | Says |
|---|---|
| Toggled on | "Listening." |
| Toggled off | "Quiet." |
| Battery low | "Battery at ten percent." |

The toggle confirmations matter: one word tells you unambiguously which state you
just entered, with no ambiguity about whether the keypress registered.

---

## Things never to say

- "Here is a summary of…"
- "I've completed the task you requested."
- "It looks like there might be an issue."
- Anything containing a file path, hash, or line number
- Anything read from an unrecognized app class (`org.omarchy.agent` aloud is
  worse than silence)
- **The same sentence twice within the last 15 utterances** — enforced
  mechanically by the phrase bank's `avoid_last_n`, not left to chance

---

## How phrasing gets decided

Text on a page is not evidence about speech. So, before any phrasing is wired in:

1. Write candidate phrasings for the events in question
2. Synthesize all of them through Piper at the real settings
3. **Listen to them in sequence**, as they'd occur during actual work
4. Cut anything that sounds long, chirpy, repetitive, or unclear
5. Only then wire it in

Candidates and verdicts live in `experiments/phrasebook/`, so the reasoning
behind each choice is recoverable later.

This is now a command rather than a ritual (task 2.10):

```
experiments/build-phrasebook-audio.py    # renders WAVs + INDEX.md, plays nothing
experiments/phrasebook/play.sh           # the one thing here that makes sound
```

It stages two things, because they answer different questions.
`by-event/` plays every sampled phrasing for one moment back to back — *do these
all sound like the same system, and would the fortieth still be tolerable?*
`session/` plays a plausible hour of work in the order it would actually happen
— *would you turn this off?* Only the second one really decides anything.

Hand-written and model-written phrasings are labelled in the index and
alternated in the audio, so the difference between them is something you hear
rather than something you are told.

The specific thing to listen for: **imagine hearing this particular sentence for
the fortieth time.** Most phrasings that pass on the page fail that test.
