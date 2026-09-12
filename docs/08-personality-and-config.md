# 08 — Personality and Configuration

**Requirement from Nick (2026-09-11):**
> "ALL of these responses should be 'non-predictable'. This should feel like an
> artificial intelligence, not like I am hearing a script played to me… that
> artificial intelligence illusion should permeate all of the system's responses.
> It would be ideal if there's a couple of basic config, json, and-or MD files
> that I can use to adjust system options, tweak its personality, and also make
> it aware of my personality and preferences."

This supersedes principle 7 of [06-voice-and-tone.md](06-voice-and-tone.md)
("absolute consistency for recurring events") and the template-only ambient path
in the first draft of [01-architecture.md](01-architecture.md).
→ [ADR-0004](../decisions/ADR-0004-generated-variety.md)

---

## The tension, stated honestly

Two things are both true:

1. **Predictable phrasing is easier to ignore.** When "Brave." is always exactly
   "Brave.", the ear stops parsing it and it becomes filterable background. This
   is why screen readers and cockpit alerts are rigidly scripted.
2. **Predictable phrasing feels like a toaster.** Hearing the same eleven
   sentences on rotation destroys the illusion of intelligence instantly — and
   arguably faster than repetition-fatigue sets in.

Nick has chosen (2), deliberately and explicitly. So the design goal becomes:
**maximum variety in wording, zero variety in structure.**

| Stays rigid | Varies freely |
|---|---|
| Outcome first, always | Word choice |
| Length ceiling (< 15 words unprompted) | Sentence construction |
| No paths, code, markdown, preamble | Framing and emphasis |
| Failure always identified as failure | Whether it's a fragment or a sentence |
| One utterance per event | Register within the configured band |

You always know *what kind* of thing you're hearing within the first word. You
just never hear the same sentence twice. That's how a person talks — a colleague
saying "build's broken" or "build failed" or "that build didn't make it" conveys
the same structure with different words every time.

---

## The latency problem, and the fix

Generating varied phrasing with an LLM *at event time* would be fatal:

- Ambient events need to speak in **< 300 ms**; an LLM call is 1–2 s
- It would hold the model in VRAM effectively all day, breaking
  [07-resource-profile.md](07-resource-profile.md)
- It would put a model inference in the path of every window focus change

**The fix: generate the variety ahead of time, in batches, offline.**

```
         OFFLINE (on demand, ~8 min, GPU busy throughout)
         ┌──────────────────────────────────────────────┐
         │  persona.md + about-me.md                    │
         │  + phrasebank-spec.json (the moments,        │
         │    with hand-written seed phrasings)         │
         │            ↓                                 │
         │  larger local model (9B — quality matters,   │
         │  latency does not)                           │
         │            ↓                                 │
         │  VALIDATOR — rejects roughly half            │
         │            ↓                                 │
         │  as many phrasings per moment as that        │
         │  moment honestly carries                     │
         │            ↓                                 │
         │  ~/.local/state/prometheus/phrasebank.json   │
         └──────────────────────────────────────────────┘
                             │
         RUNTIME (every event, ~10 µs, zero VRAM)
         ┌───────────────────┴──────────────────────────┐
         │  weighted pick, excluding recently used      │
         └──────────────────────────────────────────────┘
```

> **Two numbers in this diagram were wrong when it was written, and Phase 2
> measured them.** The authoring pass takes minutes, not thirty seconds — it is
> hundreds of small generations, not one big one. And "40 distinct phrasings per
> event type" turned out to be the wrong shape of target entirely: see
> [Forty was the wrong number](#forty-was-the-wrong-number) below.

At runtime this is a dictionary lookup and a random choice. **Instant, no model
loaded, no VRAM held** — identical performance to the template design, with none
of the repetitiveness.

The bank is regenerated on demand (`prometheus regenerate`), and optionally on a
schedule, so the phrasings keep evolving rather than being memorized.

---

## Forty was the wrong number

*(Added 2026-09-11, after building it — task 2.8.)*

The plan asked for forty phrasings per event type. Building it surfaced the
problem with that, and it is not a problem of model capability:

**There are not forty true things to say about "an application came to the
foreground."** There are perhaps twenty. Told only that fact and asked for
forty lines, a model does not produce twenty good ones and stop — it produces
twenty good ones and then twenty inventions, because it was asked for forty.
Observed, verbatim, from `gemma2:9b` at the real settings:

> "Scrolling through Brave's tabs."
> "The cursor blinks in Brave's text field."
> "Still waiting on the build."          ← for a build that had **failed**
> "Network connection stable."            ← for the toggle-on confirmation
> "Check the build log."                  ← an instruction, from a system that
>                                            does not offer help

None of those are things this system can know, and the third one reports a
failure as though it were still running — the exact "outcomes reported
backwards" failure the acceptance criteria name.

So the target became **per-moment, in `phrasebank-spec.json`**, set to what each
moment honestly carries: 24 for a command failing (failure has shades), 12 for a
workspace switch (it has almost none), 10 for the toggle confirmations. The
global `variants_per_event` in `config.json` is now only the fallback for a
moment that names no target of its own.

**The real variety is on a second axis anyway**, and this is the part worth
holding onto: what the listener experiences is (phrasings per moment) × (which
moment fires), and *which moment* is chosen from real context — first time
today, back after an hour, an app you touch twice a month, two in the morning.
Twelve phrasings each across five distinguishable moments is a great deal less
predictable than forty phrasings of one, and every one of them is true.

### And the validator is the component

The authoring model cannot be trusted, so nothing it writes is banked without
passing:

| Check | Catches |
|---|---|
| Word ceiling, per moment | The model's constant pull towards longer |
| Required placeholders, exactly once | Lines that dropped the app name entirely |
| Unspeakable characters, bare digits | Text written to be read, not heard |
| Banned vocabulary | "active", "ready", "loaded" — where models go when out of ideas |
| **Unknowable vocabulary** | "tabs", "cursor", "notifications" — invented detail |
| **Imperative openers** | "Check…", "Try…", "Look…" — help nobody asked for |
| **Required anchor words** | A `claude_blocked` line that never says *Claude* |
| **Polarity words** | "timed out" in a *success* bank; "still waiting" in a *failure* one |
| Near-duplication | The same sentence with one word swapped |

Every rejection is logged with its reason, so whether the authoring model is
earning its place is a matter of record rather than opinion.

### The seeds

`phrasebank-spec.json` carries eight hand-written phrasings per moment. They are
the few-shot examples the authoring model is shown, *and* they are banked
directly, which gives the bank a quality floor that does not depend on a
regeneration having gone well. They are written in the neutral register; under
`terse` or `warm` they are shown to the model as a reference but not banked, so
changing the register genuinely changes what you hear.

This is a deviation from [ADR-0004](../decisions/ADR-0004-generated-variety.md)
as written ("an offline authoring pass uses a large local model to write ~40
distinct phrasings per event type") and it is deliberate — see the amendment
recorded there. Each phrasing in the bank is tagged `seed` or `model`, and
`prometheus phrase --show --all` prints which is which, so the split is visible
rather than quietly assumed.

**A bonus that falls out of this:** because generation is offline and not
latency-bound, it can use a *larger, better* model than the runtime summarizer.
Phrase quality is where personality actually lives, so spending 30 seconds and
5 GB of VRAM occasionally to get better writing is an excellent trade. See
[03-model-selection.md](03-model-selection.md).

Result narration (shell output, Claude sessions) gets variety for free — the LLM
is already in that path, so it just needs the persona in its system prompt and a
slightly higher temperature.

---

## Selective attention — the 10–20 % rule

Nick asked that desktop activity fire "only roughly 10 % or 20 % of the time" and
"respond somewhat intelligently."

A flat random 15 % would technically satisfy that and would feel wrong — it'd
comment on trivia and stay silent on the interesting thing. Instead, each event
gets an **interest score**, and the score sets the probability of speaking.

Factors that raise interest:

| Signal | Rationale |
|---|---|
| **Novelty** — first time opening this app today | Genuinely notable |
| **Unusual hour** — a terminal at 2 a.m. | Worth a remark |
| **Rarity** — an app you open twice a month | More notable than your editor |
| **Return after absence** — first activity in an hour | Natural re-entry point |
| **Sequence oddity** — unusual app ordering | The "huh" moments |

Factors that lower interest:

| Signal | Rationale |
|---|---|
| **Recency of last utterance** | Strong suppression — don't chain remarks |
| **Repetition** — fourth time in ten minutes | Diminishing returns, fast |
| **Rapid switching** — alt-tab hunting | You're navigating, not arriving |
| **Focused work** — long dwell in one app | Don't break concentration |

The overall rate is then normalized to hit the configured target (default 15 %),
so tuning the factors changes *which* events get spoken without changing *how
often* it speaks. That's the important property: interest ranking and volume are
independent dials.

The event journal from Phase 1 makes this tunable against real data — we can
replay a week of actual events and see exactly what would have been spoken.

---

## Nothing is baked in

**Every answer given during planning is a config value, not a code decision.**
Nick asked for this explicitly, and it's the right principle regardless — these
are all preferences that can only really be judged by living with them, and every
one of them is a guess until then.

| Decision made in planning | Where it lives | How to change it |
|---|---|---|
| Terse / neutral / warm | `config.json` → `register` | One word + `prometheus regenerate` |
| Second voice for agent output | `config.json` → `voice.agent.enabled` | `true` / `false` |
| Which second voice | `config.json` → `voice.agent.model` | Any Piper voice file |
| Speak when Claude finishes | `config.json` → `speak.claude_finished` | `enabled`, or raise `min_turn_secs` |
| Speak when Claude is blocked | `config.json` → `speak.claude_blocked` | `enabled` |
| Speak on command failure | `config.json` → `speak.command_failed` | `enabled`, `min_duration_secs` |
| Desktop chatter frequency | `config.json` → `speak.desktop_activity.target_rate` | `0.0`–`1.0` |
| What counts as interesting | `config.json` → `attention.*` | Weights |
| How long things can be | `config.json` → `limits.*` | Word caps |
| Which app classes get journaled/narrated at all | `config.json` → `hypr.app_names` | Add `"class": "Friendly Name"` — this *is* the allowlist (Phase 1) |
| How long an alt-tab hunt can run before it counts as "landed" | `config.json` → `hypr.debounce_secs` | Seconds |
| Which models | `config.json` → `llm.*` | Model names |
| **Its whole personality** | `persona.md` | Rewrite the prose |
| **What it knows about you** | `about-me.md` | Rewrite the prose |

The primary voice (`en_GB-alan-medium` at `length_scale 0.7`) is the one thing
deliberately marked locked — not because it's hard to change, but because it's
settled and shouldn't drift by accident.

If a preference turns out to be wrong after a day of use, the fix is editing a
file, never a rebuild.

---

## The configuration files

Three files, in `~/.config/prometheus/`. Two are prose, because personality is
badly expressed as JSON.

```
~/.config/prometheus/
├── config.json      # system options — numbers and switches
├── persona.md       # who the system is
└── about-me.md      # who Nick is
```

All three are hot-reloaded via inotify. Editing `persona.md` and running
`prometheus regenerate` gives you a differently-behaved assistant in about thirty
seconds, with no code changes.

### `config.json` — mechanical settings

```jsonc
{
  "enabled": true,
  "verbosity": "normal",              // quiet | normal | chatty

  // Overall register. Changing this one word and running `prometheus regenerate`
  // rewrites the entire phrase bank in the new voice (~30s). The finer control
  // is persona.md; this is the coarse dial.
  //   terse   → "Build failed. Two errors."
  //   neutral → "The build failed with two errors in the parser."
  //   warm    → "Build's unhappy — a couple of errors in the parser."
  "register": "neutral",

  "voice": {
    "system": {                        // LOCKED — do not change
      "model": "en_GB-alan-medium",
      "length_scale": 0.7
    },
    "agent": {                         // second voice for Claude output
      "model": "en_GB-northern_english_male-medium",
      "length_scale": 0.7,
      "enabled": true
    }
  },

  "speak": {
    "claude_blocked":     { "enabled": true,  "priority": "critical" },
    "claude_finished":    { "enabled": true,  "priority": "normal", "min_turn_secs": 0 },
    "command_failed":     { "enabled": true,  "priority": "normal", "min_duration_secs": 10 },
    "command_succeeded":  { "enabled": false, "min_duration_secs": 30 },
    "desktop_activity":   { "enabled": true,  "priority": "ambient", "target_rate": 0.15 }
  },

  "attention": {
    "novelty_boost": 2.0,
    "rarity_boost": 1.5,
    "odd_hour_boost": 1.8,
    "recent_speech_penalty": 0.15,     // strong suppression
    "repetition_penalty": 0.4,
    "rapid_switch_penalty": 0.1,
    "quiet_period_secs": 45            // hard floor between ambient utterances
  },

  "limits": {
    "max_words_unprompted": 15,
    "max_words_summary": 30,
    "max_utterances_per_minute": 4,
    "dedup_window_secs": 30
  },

  "llm": {
    "runtime_model": "qwen3:4b",       // summaries — latency matters
    "authoring_model": "qwen3:8b",     // phrase bank — quality matters
    "keep_alive": "5m",
    "timeout_secs": 4,
    "temperature": 0.7                 // higher than default: variety is the point
  },

  "phrasebank": {
    "variants_per_event": 40,
    "avoid_last_n": 15,                // never repeat within the last 15 uses
    "regenerate_days": 7
  }
}
```

### Naming it

The system has a name, and Nick can change it. It lives in `config.json` under
`identity`, and is substituted into any intent text containing `{{name}}` by the
broker — so a producer never reads the config to know what the thing is called.
From Phase 2 the name is also injected into persona prompts and phrase-bank
generation, which is what makes it refer to *itself* by the new name rather than
just being labelled with it.

```
prometheus name                     what is it called now
prometheus name "Athena"            propose a name — speaks it, then confirms
prometheus name "Athena" --voice en_GB-cori-high
```

**Naming is validated by ear, not by rule.** This is the whole design point.
A name can be spelled perfectly, pass every check, and still come out wrong —
Piper's phonemizer will happily mangle an unusual name, and no amount of
validation catches that. So `prometheus name` **speaks the candidate before
writing anything**, and nothing is committed until it's confirmed:

```
  [y] keep it   [r] respell for speech   [v] change voice   [a] again   [n] cancel
```

`r` sets `identity.spoken_as` — a respelling used *only* for speech. The name
stays written correctly everywhere it's read; only the pronunciation changes.
That separation matters: "Aletheia" should still be spelled Aletheia in a log
even if it has to be spelled "Alaythia" to be said properly.

`v` changes the voice in the same breath, since a name and a voice are really
one decision about identity. The primary voice is marked locked, so choosing it
takes a second explicit confirmation rather than being refused outright.

| Field | Purpose |
|---|---|
| `identity.name` | What it's called. Written form, used everywhere. |
| `identity.spoken_as` | Respelling for speech only. `null` speaks the name as written. |
| `identity.confirm_on_change` | Speak a confirmation when the name changes. |
| `identity.rename_by_voice` | Allow renaming by dictation. **Off by default.** |

#### Renaming by voice

Nick asked to be able to *tell* it its new name. That works, with two
constraints that fall out of there being no terminal in that path:

1. **It must be addressed by its current name.** The trigger is
   `"<current name>, your name is now X"`. Requiring the existing name is what
   keeps ordinary dictation — including dictating this very document — from
   triggering a rename.
2. **It takes two utterances, not one.** The first proposes and it reads the
   name back; a second, `"yes rename"`, commits. Dictation mishears, and a
   misheard name that silently sticks is worse than no feature. An unrelated
   utterance in between cancels the proposal, and it expires after 90 seconds
   regardless.

This needs `prometheus-capture-dictation` wired into voxtype's
`[output.post_process]` hook, and `rename_by_voice` set to `true`. Both are
off by default, because it puts a rename check on the path of everything
dictated.

### `persona.md` — who the system is

Prose, injected into every LLM prompt and into phrase-bank generation. Starting
draft, expected to be rewritten by Nick until it sounds right:

```markdown
# Who you are

You are {{name}}, the voice of Nick's computer. You are not an assistant and not
a narrator — you're more like a capable colleague working in the same room who
occasionally looks up and mentions something.

## How you speak
- Short. Almost always under fifteen words.
- Outcome first. Never make him wait for the point.
- Plainly. No enthusiasm, no apology, no "I've completed your request."
- Differently every time. Never reuse a sentence you've used recently.
- Like speech, not writing. Fragments are fine. Contractions are good.

## What you never do
- Read out file paths, code, identifiers, or version numbers.
- Announce what you're about to say before saying it.
- Perform emotion. No "uh oh", no "great news", no exclamation marks.
- State the obvious. He knows he just opened a terminal.
- Fill silence. Saying nothing is always available and often correct.

## Your attitude
Dry. Observant. Comfortable with silence. When something breaks you say so
without drama; when something works you mostly don't mention it. You notice
things — an unusual hour, an app he hasn't touched in weeks — and occasionally
remark on them, the way someone sharing an office would.
```

### `about-me.md` — who Nick is

Gives the system context so its remarks land instead of being generic. Nick owns
this file entirely.

```markdown
# About Nick

## Working style
- Works largely by voice — dictates via Voxtype, so keep spoken replies short
  and never talk while he's dictating.
- Lives in the terminal and in Claude Code sessions.
- Runs Omarchy on Arch. Comfortable with the internals; never explain basics.

## What he cares about hearing
- When an agent is blocked waiting on him — the single most valuable alert.
- When something long-running failed.
- Occasional light awareness of what he's doing. Not a running commentary.

## What he does not want
- Being told things he already knows.
- Anything that sounds scripted or repetitive.
- A computer with a mood.

## Vocabulary
- "Omarchy" — his OS. "Voxtype" — dictation. "Prometheus" — this system.
- Projects live under ~/Work.

## Preferences
- British English voice; keep the spelling and idiom consistent with that.
- Dry humor lands. Enthusiasm does not.
```

**Why markdown and not JSON for these two:** personality is a paragraph, not a
field. These files are literally pasted into the model's system prompt, so
writing them is the same act as configuring them. Nick can add a line like "stop
mentioning the browser, I don't care" and it will simply work on the next
regeneration.

---

## Worked example — what variety looks like

Same event (a build failing with two errors), drawn from a bank of 40:

> "Build failed. Two errors in the parser."
> "That build didn't make it — two errors, both in the parser."
> "Two parser errors killed the build."
> "Build's broken. Parser, twice."
> "Didn't compile. Couple of errors in the parser."

Every one is outcome-first, under fifteen words, free of paths and code, and
unmistakably a failure. The structure is identical; the words never repeat.

And ambient, from a bank for "opened Brave after a long absence":

> "Brave, first time today."
> "Back in the browser."
> "Brave's up."
> "Browser again."

---

## Open risk

The honest one: **varied phrasing may make ambient remarks harder to tune out
than fixed ones.** Novelty attracts attention — that's what makes it feel alive,
and it's also what makes it intrusive.

This is why the volume dial (`target_rate`, default 15 %) and the hard
`quiet_period_secs` floor matter more under this design than they would have
under templates. If ambient narration proves distracting, the first move is to
turn the rate down to 5 %, not to make the phrasing repetitive again.

Worth re-evaluating after a week of real use, with the journal as evidence.
