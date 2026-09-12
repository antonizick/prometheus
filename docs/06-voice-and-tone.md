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

---

## What the Phase 5 pass found

*(2026-09-12 — see [notes/2026-09-12-phase-5.md](../notes/2026-09-12-phase-5.md).
The listening review itself is Nick's; this is the audit that preceded it, and
what it changed.)*

It took **five regenerations**, and each one produced a *different* family of
bad phrasings once the previous family was blocked:

```
1. invented detail          "Files changed, Claude Code."
2. computer-science nouns   "New Brave process launched."
3. personification          "Brave, humming quietly tonight."
4. self-narration           "Lucent is aware Brave is opening."
   + prediction             "Long night ahead in Brave."
5. on-screen furniture      "Brave's interface shows itself."
   + polarity               "Claude processing input on Prometheus."   <- BLOCKED
```

That is the finding rather than an accident of process: **a validator tightened
against what a model did last time tells you nothing about where it will go
next**, and it goes somewhere new every time it runs out of true things to say.

So the bank was left **clean rather than converged**, and what bounds the
problem is not a longer word list. It is the seeds (134 hand-written lines,
not one of which failed any check in any round), the permanence of vetoes, and
the audit below — run after *every* regeneration, not once.

Auditing the generated bank turned up **53 phrasings cut** across several
distinct failure modes, all exclusively in model-written lines — not one
hand-written seed failed any check, old or new.

**1. Invented detail.** The bank contained, for a window merely gaining focus:

> "Files changed, Claude Code."
> "Brave blinks briefly."
> "Prompt waiting patiently in the terminal."

None of those are things this system can know. And one was worse than invented —
`claude_blocked_project` carried *"Claude Code's running on Prometheus."*, which
reports a **blocked** agent as running: the exact "outcomes reported backwards"
failure the acceptance criteria name.

The pattern is worth stating plainly, because it will recur at every
regeneration: **asked to say something about a bare focus change, a model
reaches for a detail that would make it interesting, and every detail available
to it is one it invented.** This is the same force that made forty-per-moment
the wrong target in [08](08-personality-and-config.md); it simply survived at
smaller numbers.

**2. Computer-science vocabulary.** A distinct habit, and one the original
banned list did not touch — it was aimed at *corporate* filler ("active",
"ready", "successfully"):

> "New Brave process launched."   "Obsidian session beginning."
> "Claude's input queue empty."   "Another thread asking from Claude…"

A session and a queue are not things you hear about, they are things a program
has. Principle 3 again: he knows he opened an app, and being told a "process
launched" is the same fact in a worse costume.

**And one defect that only sound reveals.** The bank contained
*"Claudes awaits your response."* The missing apostrophe is nearly invisible on
this page and unmistakable out loud. That is the entire argument for this
section — a text review cannot catch it. It is now a validator rule
(`plural_proper_noun`), along with a check that a phrasing ends like a sentence
at all, after *"Brave session freshly started"* was banked with no full stop.

All are vetoed permanently, and the vocabulary that admitted them is in the
spec's `banned_words` and `unknowable_words`, so regeneration cannot bring the
family back.

### The last three were found in the transcript, not the bank

Worth separating, because the method matters. Reading what the system had
*actually said* during the day — `prometheus transcript`, not `phrase --show` —
turned up this, spoken aloud:

> "Claude's waiting on your input— Prometheus."

A missing space before the em-dash: a typo on the page, a missing beat out
loud. Pulling on it found two more, all three in `claude_blocked_project` —
the most valuable alert the system has:

| line | defect |
|---|---|
| `"…your input— {project}."` | no space before the em-dash |
| `"Answer needed for Claude - {project}."` | hyphen where every seed uses an em-dash; Piper phrases them differently |
| `"He's stuck in {project} - Claude."` | **`he` is a banned word** — and Claude is stuck, not "he" |

The last is the instructive one. `he` / `him` / `his` are banned precisely to
stop the system talking about Nick in the third person, and the check passed
anyway: `normalise()` closes apostrophes up so `"didn't"` stays one token, and
that same rule turns `"he's"` into `"hes"`, which `" he "` never matches. **The
ban had a hole exactly the width of a contraction.**

Now three more validator rules — `banned_word_contraction`, `dash_spacing`,
`hyphen_as_dash` — and eight more lines cut.

**This is the argument for the listening review in one paragraph.** Everything
above was found by auditing the bank; these were only findable downstream of
the speaker. A phrasing can pass every static check the validator has and still
be wrong in a way that only shows up as sound.

### The audit, as a routine

Run this after any `prometheus regenerate`. It takes a couple of minutes and it
found something new on all four attempts — the word lists only catch what the
model did *last* time.

```bash
prometheus-phrasebank verify          # the mechanical rules, first

# 2. Draw one line per moment exactly as the runtime would. This is what
#    surfaced "Lucent is aware Brave is opening." — nothing static caught it.
for m in app_first_today app_returned app_rare app_odd_hour app_opened; do
  printf '%-20s ' "$m"; prometheus phrase $m --slot app=Brave -n 1
done

# 3. Read what it has actually been saying. Three defects were only ever
#    visible here, after passing every check above.
prometheus transcript -n 40

# 4. Then listen.  ⚠ MAKES SOUND
experiments/build-phrasebook-audio.py
experiments/phrasebook/play.sh session
```

What to look for, in the order the failures actually appeared: detail it cannot
know, computer-science vocabulary, personification, the system naming itself,
and guesses about what happens next. Cut with
`prometheus-phrasebank veto <moment> "<the words>"` — permanent, and survives
every future regeneration.
