# 10 — Feedback and Tuning

How to tell this system it's wrong, and how to fix it — during the build, and
for as long as you live with it afterwards.

Everything here is a file you edit or a command you run. Nothing in this
document requires a rebuild, and nothing requires me.

---

## The two rules that make the rest work

**1. Capture the verdict at the moment you have it.** The thing that will
annoy you in month three is not something you will remember in month four. The
moment an utterance lands wrong is the moment you know exactly why — two
seconds later you're back in the work, and it's gone.

```bash
prometheus feedback "that one broke my concentration"
prometheus feedback                    # just mark the moment, no note
```

That writes your note *plus the last few things it actually said*, plus what
the dials were set to at the time, to
`~/.local/state/prometheus/feedback.jsonl`. A month later,
`prometheus feedback --list` is a reviewable record of your own reactions
rather than a vague sense that it talks too much.

**It's on a key**, next to the other four in `~/.config/hypr/bindings.lua`:

| Keys | Action |
|---|---|
| `SUPER + ALT + N` | **Note** — record this moment, with the evidence attached |

Bound with no argument it records a bare marker, which is enough on its own:
the transcript stapled to it says what provoked you. Add words later, or run
`prometheus feedback "..."` from a terminal when you have them.

*(`N` for note, not `F` for feedback — `SUPER+ALT+F` is already Omarchy's
"Full width". Same collision that moved this whole family off `SUPER+SHIFT`.)*

**2. Change one dial at a time, and give it a day.** Every setting here
interacts with the others, and your reaction to speech is heavily
mood-dependent. Change `target_rate`, live with it, then change something else.
Changing three things and concluding "it's better now" teaches you nothing
about which of the three mattered.

---

## Part 1 — Feedback during the build

While we're still building, the loop is: *you listen, you tell me what's
wrong, I change the thing that's wrong.* What makes that efficient is being
specific about **which layer** is wrong, because they have completely different
fixes.

### The four layers, and how to tell them apart

| What you noticed | Layer | Who fixes it |
|---|---|---|
| "It said something it shouldn't have said at all" | **Policy** — when it speaks | `config.json`, or me |
| "It should have said something and didn't" | **Policy** | `config.json`, or me |
| "The wording was wrong / grated / sounded fake" | **The phrase bank** | You, directly — see Part 3 |
| "The voice itself is wrong" | **Voice** | `prometheus audition`, `config.json` |
| "It spoke over me / too slow / cut off" | **Mechanics** | Me — that's a bug |

When you report something, the most useful thing you can give me is not a
description — it's the evidence, and it's already on disk:

```bash
prometheus transcript -n 40 -v     # everything said, and everything DROPPED and why
prometheus feedback --list         # your own notes, with context attached
prometheus journal -n 40           # what the desktop was actually doing
prometheus log -f                  # the daemon's reasoning, live
```

`prometheus transcript` is the one to reach for first. It shows the utterances
that were *suppressed* as well as the ones you heard, with the reason — so
"why didn't it tell me?" is usually answered in one line without guessing.

### Auditioning phrasings before they go live

The review gate from [04-build-plan.md](04-build-plan.md) is a command:

```bash
experiments/build-phrasebook-audio.py          # renders WAVs + INDEX.md, silent
cat experiments/phrasebook/INDEX.md            # read first — `*` hand-written, `~` model
experiments/phrasebook/play.sh                 # ⚠ THIS MAKES SOUND
experiments/phrasebook/play.sh command_failed  # one moment's phrasings, back to back
```

The question to hold while listening is never "is this a good sentence". It's
**"would I still be happy hearing this the fortieth time?"** Most phrasings
that read fine fail that test, and you can only find out by ear.

### Trying a policy change without living through it

You don't have to wait a week to see what a setting would do. The replay
harness runs the attention scoring over your *real* journal history and tells
you what would have been spoken:

```bash
experiments/replay-scoring.py                  # current weights
experiments/replay-scoring.py --rate 0.05      # what 5% would have felt like
experiments/replay-scoring.py --verbose        # per-event: spoke / stayed quiet, and why
```

This is the cheapest tuning you can do, and the only kind that uses evidence
instead of imagination. Run it before asking for a change to the weights.

### Checking nothing broke

```bash
experiments/run-acceptance.sh        # every Phase 0 criterion, re-measured
experiments/test-phrasebank.py       # the runtime guarantees
prometheus-phrasebank verify         # every phrasing still valid
experiments/measure-overhead.sh      # the resource contract
```

---

## Part 2 — Tuning once you're living with it

### The three questions, and the dial for each

Almost every reaction you will have reduces to one of these. They are
independent on purpose — you can make it speak *less often* without changing
*what it considers interesting*, and vice versa.

#### "It talks too much / not enough" → volume

`~/.config/prometheus/config.json`:

```jsonc
"speak": {
  "desktop_activity": { "enabled": true, "priority": "ambient",
                        "target_rate": 0.15 }   // <- this one
},
"attention": {
  "quiet_period_secs": 45      // hard floor between ambient remarks
},
"limits": {
  "max_utterances_per_minute": 4
}
```

`target_rate` is the fraction of eligible desktop events it speaks on. **This
is the first dial to reach for, always.** If ambient narration is intrusive,
turn it down to `0.05` — do not make the phrasing repetitive again, which is
the trap [08](08-personality-and-config.md) warns about.

`quiet_period_secs` is a hard floor: no ambient remark within this many seconds
of the last one, regardless of how interesting. Raise it to 120 and the system
becomes noticeably calmer without becoming less useful, because the *valuable*
utterances (a blocked agent, a failure) aren't ambient and aren't subject to it.

Takes effect immediately — the config is hot-reloaded via inotify. No restart.

#### "It's interested in the wrong things" → attention

```jsonc
"attention": {
  "novelty_boost": 2.0,        // first time opening this today
  "rarity_boost": 1.5,         // an app you touch twice a month
  "odd_hour_boost": 1.8,       // a terminal at 2am
  "recent_speech_penalty": 0.15,
  "repetition_penalty": 0.4,
  "rapid_switch_penalty": 0.1
}
```

Raise what you want to hear about, lower what you don't. The overall rate is
normalised afterwards, so **changing these changes *which* events get spoken
without changing *how often* it speaks.** That's the property that makes them
safe to experiment with.

Check your change against real history before committing to it:

```bash
experiments/replay-scoring.py --verbose
```

#### "I never want to hear about that application" → the allowlist

```jsonc
"hypr": {
  "app_names": {
    "brave-browser": "Brave",
    "foot": "the terminal",
    "discord": "Discord"        // delete this line and Discord vanishes entirely
  }
}
```

This map **is** the allowlist. An app class with no entry is never journaled
and never narrated, no matter what it does. Deleting a line is the complete,
permanent fix for "stop mentioning X". Adding one is how you teach it a new
app — find the class with `prometheus log -f` while focusing the window.

#### "It should be quieter about everything, right now" → verbosity

`SUPER + ALT + V` cycles `quiet → normal → chatty` live. `quiet` is workspace
switches only. This is the dial for a bad afternoon, not for a preference —
preferences belong in the config file, where they survive a reboot.

And `SUPER + ALT + X` cuts the current utterance mid-word, instantly,
without disabling anything. Use it freely; it's what makes leaving the system
on tolerable.

### What to do at a week, a month, six months

**After a week.** You will have a handful of `prometheus feedback` notes and a
real journal. Read them together:

```bash
prometheus feedback --list
experiments/replay-scoring.py --verbose | less
```

Look for *one* pattern, not five. The likely ones: it's too chatty (lower
`target_rate`), it interrupts concentration (raise `quiet_period_secs`), or one
particular application is noise (delete it from `app_names`). Make one change.

**After a month.** By now you'll have opinions about wording, not just volume.
This is the point to re-run the listening review and cut what grates:

```bash
experiments/build-phrasebook-audio.py
experiments/phrasebook/play.sh           # ⚠ makes sound
prometheus-phrasebank veto app_returned "Claude Code's been left running"
```

Also the point to consider `register`. If everything feels a touch verbose:
change `"register": "neutral"` to `"terse"` and run `prometheus regenerate`.
That rewrites the whole bank in the new voice — about fifteen minutes of GPU,
with nothing waiting on it.

**After six months.** The interesting question stops being "is this annoying"
and becomes "what has it never said that I wish it would". That's a change to
`phrasebank-spec.json` — a new moment, with its own seeds — and it's the point
where it's worth a conversation rather than a config edit.

Also worth doing occasionally regardless: `prometheus regenerate`, so the
phrasings keep moving rather than becoming a script you've memorised. The bank
goes stale automatically after `regenerate_days` (7) and after any edit to
`persona.md`, `about-me.md`, or the spec.

### The two prose files — the real personality dial

```
~/.config/prometheus/persona.md      who it is, how it speaks
~/.config/prometheus/about-me.md     who you are, what you want to hear
```

These are pasted verbatim into every model prompt and into phrase-bank
generation, so **editing them is configuring it**. Add a line to `about-me.md`
like:

> - Never mention the browser. I don't care what it's doing.

...run `prometheus regenerate`, and it will simply be true of every phrasing it
writes from then on. This is the most powerful and least mechanical control in
the system, and the one most worth actually using.

Changing either file marks the bank stale, and it regenerates on its own in the
background rather than making you wait.

---

## Part 3 — Yes, there is a bank of messages you can edit

This is the direct answer to your question, and the honest version has three
parts, because there are three files and only two of them are yours.

| File | What it is | Edit it? |
|---|---|---|
| `~/.config/prometheus/phrasebank-spec.json` | **The source.** The 17 moments, and eight-plus hand-written phrasings for each. | **Yes — this is the one you want.** |
| `~/.local/state/prometheus/phrasebank.json` | The **generated** bank — 284 phrasings, what it actually reads from. | Editable, but overwritten by the next `regenerate`. |
| `~/.local/state/prometheus/phrasebank-vetoed.json` | Lines you've cut by ear. Never re-banked. | Managed by `veto`; hand-editable. |

**The trap to avoid:** hand-editing `phrasebank.json` works, and takes effect
instantly, and is silently lost the next time the bank regenerates — which
happens on its own whenever you edit `persona.md` or the spec. Put anything you
want to keep in the **spec**.

### Two commands, so you don't have to hand-edit anything

```bash
# Cut a line you never want to hear again. Gone now, and gone from every
# future regeneration.
prometheus-phrasebank veto claude_finished "The prompt vanished for Claude"

# Write one of your own. Goes into the spec, so regeneration keeps it.
prometheus-phrasebank add app_returned "Back at {app}, then."
prometheus-phrasebank add command_failed "{command}'s in the bin." --force
```

`add` validates what you write against that moment's rules — word ceiling,
required placeholders, no invented detail — and refuses if it objects. **Your
ear beats the validator**: `--force` adds it anyway. It also clears any earlier
veto on the same line, so `add` is how you change your mind.

Both take effect immediately *and* permanently. `add` re-stamps the bank so one
new line doesn't trigger a needless fifteen-minute regeneration.

### Reading what it currently has to say

```bash
prometheus phrase --show                    # all 17 moments, with counts
prometheus phrase --show command_failed     # every phrasing for one moment
prometheus phrase app_opened --slot app=Brave -n 5    # draw five, as it would
```

In `--show`, `*` marks a hand-written phrasing and `·` one the model wrote.
If you find yourself vetoing mostly `·` lines, that's the signal that the
authoring model isn't earning its place — tell me and we'll change it.

### Editing the spec directly

Nothing stops you, and for anything structural it's the right move:

```bash
$EDITOR ~/.config/prometheus/phrasebank-spec.json
prometheus-phrasebank verify      # did I break anything?
prometheus regenerate             # rebuild around the change
```

It's JSON-with-comments, and the comments explain each field. The fields worth
knowing:

| Field | What it controls |
|---|---|
| `seeds` | Your phrasings. Always banked, never invented. **Add here.** |
| `target` | How many phrasings this moment should carry. |
| `max_words` | The ceiling, measured on the *spoken* line. |
| `moment` | What the model is told happened. Vague description → vague phrasings. |
| `banned_words` / `unknowable_words` | Vocabulary that gets a candidate rejected. |
| `must_include_any` | Words a phrasing must carry, or it isn't that alert. |
| `allow_words` | Per-moment exceptions to the above. |

Editing the spec changes its fingerprint, which marks the bank stale and
triggers a background regeneration. That's intended: the spec is the source,
the bank is the build output.

---

## Recipes

| You say | Do this |
|---|---|
| "It's too chatty." | `target_rate` → `0.08`. Live with it a day. |
| "It interrupts when I'm concentrating." | `quiet_period_secs` → `120`. |
| "It talks while I'm dictating." | That's a bug, not a setting — mic gating is supposed to be absolute. Tell me. |
| "Stop mentioning Discord." | Delete `"discord"` from `hypr.app_names`. |
| "I hated that specific sentence." | `prometheus-phrasebank veto <moment> "<the words>"` |
| "I want it to say X instead." | `prometheus-phrasebank add <moment> "X"` |
| "It's too wordy in general." | `"register": "terse"`, then `prometheus regenerate`. |
| "It's too cold." | `"register": "warm"`, then `prometheus regenerate`. Warm is *less clipped*, never cheerful. |
| "It missed something important." | `prometheus transcript -n 40 -v` — if it's there marked dropped, the reason is on the line. |
| "It never shuts up about one app." | `repetition_penalty` → `0.2`, or remove the app. |
| "I want it silent for an hour." | `SUPER + ALT + P`. It's a power switch, not a mute — zero processes, zero VRAM. |
| "The phrasings feel stale." | `prometheus regenerate`. |
| "I want a whole new thing it can say." | New entry in `phrasebank-spec.json` — worth doing together the first time. |

---

## What not to do

- **Don't make the phrasing repetitive to make it ignorable.** That was the
  original design and you overruled it for good reason. Turn the *rate* down
  instead. ([ADR-0004](../decisions/ADR-0004-generated-variety.md))
- **Don't hand-edit `phrasebank.json`** and expect it to survive. Use the spec.
- **Don't change `voice.system`.** It's marked locked because it's settled;
  drifting it by accident costs you the thing that makes the system feel like
  one system.
- **Don't set `llm.keep_alive` to `-1`.** It holds the GPU hostage all day and
  breaks the resource contract in [07](07-resource-profile.md).
- **Don't tune three things at once.** You'll learn nothing from the result.
- **Don't tune from memory.** `prometheus feedback --list`,
  `prometheus transcript`, and `experiments/replay-scoring.py` all exist so you
  don't have to.

---

## Where everything lives

```
~/.config/prometheus/
├── config.json             all the numbers and switches — hot-reloaded
├── persona.md              who it is                  } regenerate after
├── about-me.md             who you are                } editing either
└── phrasebank-spec.json    what it has occasion to say, and your phrasings

~/.local/state/prometheus/
├── phrasebank.json         the generated bank — build output, not source
├── phrasebank-vetoed.json  lines you cut by ear, permanently
├── feedback.jsonl          your notes, with evidence attached
├── transcript.jsonl        everything said — and dropped, with reasons
├── journal                 what the desktop did
└── *.log                   per-component reasoning, including every phrase
                            candidate and why it was accepted or rejected
```

Config and state are left alone by `./install.sh --uninstall`, so none of your
tuning is at risk from a reinstall.
