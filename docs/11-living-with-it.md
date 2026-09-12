# 11 — Living With It

*(The operator's manual — task 5.7. Written 2026-09-12, at the point where the
building stops and the using starts.)*

[10](10-feedback-and-tuning.md) is the *narrative*: how to think about tuning,
which layer is wrong, what to do at a week and a month. This document is the
*reference*: exactly what to do now, exactly what each dial is called, exactly
what it does, and exactly how the feedback machinery works underneath.

If you read one section, read [**§2 — The next two days**](#2--the-next-two-days).
If you need a dial in a hurry, [**§6 — Complete tuning reference**](#6--complete-tuning-reference).

---

## 1 — Is anything left to build?

**No. Use it.** Every phase is built, the resource contract is measured and
met, and narration has been live since the end of Phase 5.

Two honest exceptions, and one of them is yours rather than mine:

| | |
|---|---|
| **5.3 — the listening pass** | **Staged, not signed off.** The bank was audited across six regenerations and 53 lines cut, but the listening review is yours by design. See [§8.1](#81--the-listening-pass-task-53). |
| **5.7 — this document** | You are reading it. Now done. |

**One defect was found and fixed while writing this**, and it matters because
it broke the feedback loop this document is about to ask you to use:

> **The live narrator held the phrase bank in memory from process start and
> never re-read it.** So `prometheus-phrasebank veto` — the command that makes
> a line you hated go away — removed it from the file and the desktop narrator
> went on saying it anyway. Caught red-handed in the logs: `"New program in
> {app} tonight."` was pruned from the bank at **05:43:50** and spoken at
> **05:44:55**.
>
> Fixed in `bin/prometheus-hypr` (`Narrator.refresh_bank()`): the bank's mtime
> is checked at pick time — a pull, not a poll, the same shape as the context
> gates — and the bank re-opened if the file changed. Restarted live at
> 06:32:38. A veto now takes effect on the next utterance.
>
> Verify it yourself if you want: `prometheus log --hypr | grep bank_reloaded`
> after a veto.

Everything else on the "left to do" list is a *decision*, not a build — and
every one of them is a decision that needs a few days of listening first.
They're in [§8](#8--decisions-waiting-on-you).

---

## 2 — The next two days

### 2.1 — Right now, once (about four minutes)

```bash
prometheus status                # 3 processes, "daemon: responding"
prometheus verbosity             # should print: normal
prometheus transcript -n 20      # what it has said so far today
```

Then set yourself up to catch the moment something lands wrong. There is only
one thing to memorise in this entire document:

> ### `SUPER + ALT + N`
> Press it the instant an utterance annoys you. No terminal, no words needed,
> no train of thought broken. It staples the last five minutes of speech and
> the current dial settings to a timestamp.

The other four keys, for completeness:

| Keys | Does |
|---|---|
| `SUPER + ALT + X` | **Shut up** — cuts the current utterance mid-word. Nothing is disabled. |
| `SUPER + ALT + P` | **Power** — off means zero processes and zero VRAM. Survives reboot. |
| `SUPER + ALT + V` | **Verbosity** — cycles quiet → normal → chatty. |
| `SUPER + ALT + B` | **Brief me** — summarises the journal since the last briefing. |

`X` is the one that makes leaving it switched on tolerable. Use it freely —
it costs nothing and it is not a judgement about the system.

### 2.2 — During the day: do nothing

Specifically: **do not tune anything for the first two days.** Your reaction to
being spoken to is strongly mood-dependent, and the single most common way to
learn nothing from a trial is to change three dials and conclude it's better.

Press `SUPER + ALT + N` when it annoys you. That's the whole job.

### 2.3 — End of each day (about two minutes)

```bash
prometheus feedback --list          # your notes, with the speech attached
prometheus transcript -n 40 -v      # everything said AND everything dropped
```

Read them together. You are looking for **one repeated pattern**, not a list of
individual complaints. A pattern is three notes that turn out to be the same
complaint; a single irritation on a bad afternoon is not data.

### 2.4 — After two days: exactly one change

Take the single most repeated pattern and make the *one* change for it from
[§6](#6--complete-tuning-reference) or the recipe table in
[10](10-feedback-and-tuning.md#recipes). Then live with that for another day
before touching anything else.

If nothing repeated — if you mostly forgot it was on — that is the system
working, and the question flips to [§8.2](#82--is-it-too-quiet): it may be
*too* quiet.

---

## 3 — What to watch for

These are specific and falsifiable on purpose. Each one is a prediction I am
making now, with what it means if it comes true, so that two days of listening
produces evidence rather than an impression.

### 3.1 — Most likely to go wrong

| Watch for | What it means | Fix |
|---|---|---|
| **You barely hear it at all** | Most likely outcome by far. `require_reason` includes `"focus"`, which is a deliberately conservative default: **1.2 utterances/hour.** | [§8.2](#82--is-it-too-quiet) — remove `"focus"`, → 4.1/hour |
| **It speaks after Claude turns you were watching** | `min_turn_secs: 45` is the *median* turn on this machine, so it speaks after ~53 % of them. Your actual rhythm may differ. | [§8.3](#83--the-claude-turn-threshold) |
| **A phrasing grates on the third hearing** | Expected, and the reason the bank is 278 phrasings rather than 11. | `prometheus-phrasebank veto <moment> "<words>"` — now effective immediately ([§1](#1--is-anything-left-to-build)) |
| **It says something it cannot know** | The recurring failure of the authoring model. Six regenerations produced six new families of it. | Veto it, then tell me — the vocabulary gap belongs in the spec |

### 3.2 — Would be a bug, tell me

| If this happens | Why it's a bug |
|---|---|
| It speaks while you are **dictating** | The mic gate is absolute and holds the queue rather than dropping. |
| It speaks while the **screen is locked** | `context_gates.screen_locked` has `allow: []` — nothing at all should pass. |
| Two things speak **at once**, or speech overlaps itself | The single-broker invariant (ADR-0001) is the foundation everything else rests on. |
| `SUPER + ALT + X` does not cut it instantly | The buffer is 50 ms deliberately so that key can be trusted. |
| **A blocked Claude is silent** | The most valuable alert in the system. `critical` is exempt from every gate except the power switch. |

For any of these, the evidence is already on disk — send me the output of:

```bash
prometheus transcript -n 40 -v
prometheus log -n 60
```

### 3.3 — Known and expected, not bugs

- **It says nothing when a window gains focus.** Correct at `normal` verbosity
  unless the focus change carried a signal (see [§5.2](#52--the-five-interest-signals)).
- **Workspace switches are silent.** They are `chatty`-only since Phase 5 —
  they were the most frequent event on the desktop and were absorbing ~90 % of
  ambient speech.
- **Closing a window says nothing, ever.** `close` is in no verbosity tier:
  you were there when it happened.
- **An app you use is never mentioned.** `hypr.app_names` *is* the allowlist —
  a window class with no entry is invisible to the whole system
  ([§6.4](#64--which-apps-exist-at-all)).
- **RSS reads ~152 MB, not 143 MB.** Piper's memory grows with use; the
  harness only ever samples a fresh one. Documented in
  [07](07-resource-profile.md) — the honest phrasing is "at budget", not
  "within it".

---

## 4 — Feedback mechanisms, exactly how they work

Five of them. They are genuinely different mechanisms, not five views of one
log, and knowing which answers which question saves you the guessing.

### 4.1 — `prometheus feedback` — your verdict, with evidence attached

**Trigger:** `SUPER + ALT + N`, or `prometheus feedback "some words"`.

**What it writes**, one JSON object per line, to
`~/.local/state/prometheus/feedback.jsonl`:

```jsonc
{
  "t": 1789209895.876,                    // unix seconds
  "note": "that one broke my concentration",   // null for a bare marker
  "config": {                             // the dials AT THAT MOMENT
    "register": "neutral",
    "verbosity": "normal",                // read live from the state file
    "target_rate": "0.15",
    "quiet_period_secs": "45"
  },
  "recent": [ /* up to 8 utterances from the last 300 seconds */ ]
}
```

The `recent` array is the point. It is pulled from `transcript.jsonl` and
includes **dropped** entries with their reason, so a note saying *"why didn't
it tell me?"* carries its own answer. The window is **300 seconds**, capped at
**8 utterances** (`FEEDBACK_CONTEXT_SECS` / `FEEDBACK_CONTEXT_MAX` in
`bin/prometheus`).

**Reading it back:**

```bash
prometheus feedback --list             # last 20 notes
prometheus feedback --list -n 100      # more
```

Output is one block per note — timestamp, the dials in brackets, your note,
then the last four utterances with `spoke` or the drop reason in the margin:

```
2026-09-12 14:22  [neutral/normal rate 0.15]
  that one broke my concentration
    14:21:44    spoke  Back in Brave.
    14:21:58  ratelimit  Claude needs you — prometheus.
```

A bare marker with no words is **fully useful on its own** — the four lines
underneath it say what provoked you. Don't feel you have to type.

### 4.2 — `prometheus transcript` — everything said, and everything swallowed

```bash
prometheus transcript -n 40          # what was spoken
prometheus transcript -n 40 -v       # + what was DROPPED, and why
prometheus transcript --spoken-only  # just the speech
prometheus transcript -f             # live
prometheus transcript --raw          # JSONL, for grep and jq
```

This is the one to reach for first, because **it is the only place a silence
has a reason.** Every rejection in the broker funnels through one `drop()`
call that records why:

| Reason in `-v` | Meaning |
|---|---|
| `empty` | No text. A producer bug. |
| `disabled` | Power switch off. |
| `verbosity` | Priority below the floor for the current tier ([§5.3](#53--verbosity-does-two-things)). |
| `gate_screen_locked` | Session `LockedHint` was true. |
| `gate_fullscreen` | A window was **fullscreen** — *maximized is deliberately not the same thing.* |
| `gate_other_audio` | Another process held a PulseAudio sink input. |
| `dedup` | Same `dedup_key` within `limits.dedup_window_secs` (30 s). |
| `ratelimit` | Category over its cap ([§6.5](#65--rate-limits)). |
| `ambient` | An ambient remark arrived while something was already speaking, and expired rather than arriving late and wrong. |

The order matters and is deliberate: gates are checked **before** dedup and the
rate limiter, so an utterance nobody could have heard doesn't consume a budget
a later audible one wants.

`gate_*` and `ratelimit` drops are the two worth noticing. A pile of
`ratelimit` means a producer is over-eager; a pile of `gate_other_audio` means
music is suppressing more than you want ([§6.3](#63--context-gates)).

### 4.3 — `prometheus journal` — what the desktop actually did

```bash
prometheus journal -n 40
prometheus journal -f
prometheus journal --raw
```

The filtered Hyprland event history: what happened, whether or not anything was
said about it. This is the *input* to the scoring, and it is what the replay
harness reads. If you think it missed an event, check here first — if it isn't
in the journal, the app isn't in `hypr.app_names` and nothing downstream ever
saw it.

### 4.4 — `prometheus log` — the reasoning

```bash
prometheus log -f                    # the daemon, live
prometheus log -n 60                 # the daemon, recent
prometheus log --hypr                # the listener: scoring and narration
prometheus log --file                # the on-disk log rather than journald
```

Structured JSONL. The lines worth knowing by name:

```bash
# Why did / didn't the desktop narrator speak?
prometheus log --hypr | grep -E 'narrate\.(speak|no_phrasing|seeded|bank_reloaded)'

# Your own Claude turn-length distribution — the evidence for §8.3
prometheus log | grep -o 'turn_secs[^,}]*' | sort -t: -k2 -n | tail -20

# An app you use that the system cannot see
prometheus log --hypr | grep unknown_class
```

That last one is how you extend the allowlist: focus the window, then look.

### 4.5 — `experiments/replay-scoring.py` — what a change *would* have done

The cheapest tuning there is, and the only kind that uses evidence rather than
imagination. It runs the real attention scoring over your real journal:

```bash
experiments/replay-scoring.py                      # current config
experiments/replay-scoring.py --verbose            # per event: spoke/quiet, and why
experiments/replay-scoring.py --hourly             # per hour, and the worst hour
experiments/replay-scoring.py --rate 0.05          # what a different target feels like
experiments/replay-scoring.py --verbosity chatty   # what a tier actually yields
experiments/replay-scoring.py --settle 3.0         # a different workspace debounce
experiments/replay-scoring.py --compare            # pre-Phase-5 scoring, side by side
```

**Run this before asking for any change to the attention weights.** Two lines
of its output matter more than the rest:

```
would speak     : 9/54 (16.7% achieved)      <- is the rate dial being honoured?
carried a reason: 9/9 (100%)                 <- or is it just a coin flip?
```

The second is the one to protect. An utterance with no reason behind it is a
random remark wearing the costume of an observation, and before Phase 5 **more
than half of them were exactly that.** If that number falls below ~90 %, the
scoring has stopped selecting for interest even if the volume still feels fine.

The scoring lives in `bin/prometheus-attention` and is **imported** by both the
harness and the live listener, so the replay's prediction and the system's
behaviour are the same arithmetic rather than two implementations that agree
until they don't.

---

## 5 — How the decision to speak is actually made

Worth four minutes, because every dial in §6 acts at exactly one of these
stages, and knowing which one stops you reaching for the wrong dial.

### 5.1 — The pipeline

```
Hyprland event
   ↓  hypr.app_names        the allowlist. No entry -> invisible, permanently.
   ↓  debounce 1.5s         alt-tabbing produces one entry, not six
   ↓  workspace settle 2.0s nine switches in nine seconds is one journey
   ↓  JOURNAL               <- prometheus journal
   ↓  Scorer                five interest signals, three penalties -> raw score
   ↓  RateController        normalises so target_rate is actually achieved
   ↓  require_reason        THE LOUDEST DIAL: no signal, no speech
   ↓  verbosity_kinds       is this kind of event speakable at this tier?
   ↓  Gate                  quiet_period_secs floor, recency, repetition
   ↓  phrase bank           no phrasing means silence, never a fallback
   ↓  INTENT  -----------> broker (prometheusd)
                              ↓  enabled?            power switch
                              ↓  verbosity floor     priority vs tier
                              ↓  context gates       locked / fullscreen / audio
                              ↓  dedup               30s on the same key
                              ↓  rate limit          per category, per minute
                              ↓  mic gate            HOLDS the queue, never drops
                              ↓  piper -> audio
```

Everything above the arrow is the desktop narrator. Everything below it applies
to **all** speech — Claude alerts, shell results, the read-aloud keys.

### 5.2 — The five interest signals

A focus change with none of these is, as far as the system can tell, exactly
like the last forty. These are what "carried a reason" counts.

| Signal | Fires when | Weight | Moment |
|---|---|---|---|
| `novel-today` | First time this app today | `novelty_boost` 2.0 | `app_first_today` |
| `rare` | An app you touch rarely | `rarity_boost` 1.5 | `app_rare` |
| `returned` | Back after `return_secs` (600) away | `return_boost` 2.5 | `app_returned` |
| `long-dwell` | You sat in one window ≥ `dwell_secs` (300) | `dwell_boost` 2.0 | `app_returned` |
| `odd-hour` | Outside your usual hours | `odd_hour_boost` 1.8 | `app_odd_hour` |

Most specific wins: an app you haven't touched in weeks that you also open at
2 am is reported as **rare**, not as late.

> Three of these were dead before Phase 5. `returned` had *never once fired* —
> its threshold was 3600 s and the longest real gap on this desktop was 3454 s.
> `dwell` didn't exist, and it turned out to be the signal with real
> discriminating power: p50 17 s, p75 89 s, p90 235 s. A focus change after
> five minutes in one window is a genuinely different event from the fourth
> alt-tab in six seconds, and that is knowable with no lookahead.

### 5.3 — Verbosity does two things

`SUPER + ALT + V` moves both at once, and they are separate mechanisms:

| Tier | Event kinds it may narrate | Lowest priority it will speak | Measured |
|---|---|---|---|
| `quiet` | `open` | `normal` — no ambient at all | 0.1/h |
| `normal` | `open`, `focus` | `ambient` | **1.2/h** |
| `chatty` | `open`, `focus`, `workspace`, `fullscreen`, `monitor` | `debug` | 4.7/h |

`critical` is exempt at every tier. Nothing here can silence a blocked agent —
that's what the power switch is for.

---

## 6 — Complete tuning reference

Every file here is `~/.config/prometheus/`. The format is **JSON with
comments** (`//`) — the comments are part of the shipped file and are safe to
keep, edit, and add to.

**All of `config.json` is hot-reloaded via inotify.** Save the file and it is
in effect — no restart, no `prometheus reload`, including the attention weights
and the narrator's own settings. The one exception is noted at
[§6.9](#69--the-one-thing-that-needs-a-restart).

After editing, if you're unsure it parsed:

```bash
prometheus log -n 5 | grep config_reloaded
```

### 6.1 — Volume: "it talks too much / not enough"

```jsonc
"speak": {
  "desktop_activity": { "enabled": true, "priority": "ambient",
                        "target_rate": 0.15 }
},
"attention": {
  "quiet_period_secs": 45
},
"limits": {
  "max_utterances_per_minute": 4
}
```

| Key | Type | Default | Effect |
|---|---|---|---|
| `speak.desktop_activity.enabled` | bool | `true` | `false` silences ambient narration entirely, leaving Claude and shell alerts. |
| `speak.desktop_activity.target_rate` | 0.0–1.0 | `0.15` | Fraction of *eligible* events spoken on. **The first volume dial, always.** Try `0.05`. |
| `attention.quiet_period_secs` | int | `45` | Hard floor between ambient remarks regardless of interest. `120` makes it noticeably calmer without making it less useful — the valuable utterances aren't ambient. |
| `limits.max_utterances_per_minute` | int | `4` | Global cap. `critical` is exempt. |

**Do not** make phrasings repetitive to make them ignorable — that was the
original design and you overruled it for good reason
([ADR-0004](../decisions/ADR-0004-generated-variety.md)). Turn the rate down.

### 6.2 — Interest: "it's interested in the wrong things"

```jsonc
"attention": {
  "novelty_boost": 2.0,        "rarity_boost": 1.5,
  "odd_hour_boost": 1.8,       "return_boost": 2.5,
  "dwell_boost": 2.0,

  "return_secs": 600,          "dwell_secs": 300,

  "recent_speech_penalty": 0.15,
  "repetition_penalty": 0.4,
  "rapid_switch_penalty": 0.1,

  "require_reason": ["focus", "workspace", "fullscreen"],

  "verbosity_kinds": {
    "quiet":  ["open"],
    "normal": ["open", "focus"],
    "chatty": ["open", "focus", "workspace", "fullscreen", "monitor"]
  }
}
```

| Key | Type | Default | Effect |
|---|---|---|---|
| `*_boost` | float ≥ 0 | see above | Multipliers on the raw score. Raise what you want to hear about. |
| `return_secs` | int | `600` | How long away counts as "returned". |
| `dwell_secs` | int | `300` | How long in one window counts as a long dwell. |
| `recent_speech_penalty` | 0–1 | `0.15` | Multiplier applied when it spoke recently. Lower = calmer. |
| `repetition_penalty` | 0–1 | `0.4` | Applied when this app was the subject last time. **Lower to `0.2` for "it never shuts up about one app".** |
| `rapid_switch_penalty` | 0–1 | `0.1` | Applied during alt-tab storms. |
| `require_reason` | list | `["focus","workspace","fullscreen"]` | **The loudest dial in the file.** Kinds listed here must carry a signal from [§5.2](#52--the-five-interest-signals), not merely win a probability draw. See [§8.2](#82--is-it-too-quiet). |
| `verbosity_kinds.<tier>` | list | see above | Which event kinds each tier may narrate. Valid kinds: `open`, `focus`, `workspace`, `fullscreen`, `monitor`. (`close` is deliberately in none.) |

**The boosts are safe to experiment with**, and this is the property worth
understanding: the rate is normalised *afterwards*, so changing these changes
**which** events get spoken without changing **how often** it speaks. You are
re-ranking, not turning a volume knob.

Check any change against real history before keeping it:

```bash
experiments/replay-scoring.py --verbose
```

If you change the weights substantially, let the controller forget the old
shape:

```bash
rm ~/.local/state/prometheus/attention-gain.json     # safe; rebuilds in a few dozen events
```

### 6.3 — Context gates

```jsonc
"context_gates": {
  "enabled": true,
  "cache_secs": 2.0,
  "screen_locked": { "enabled": true, "allow": [] },
  "fullscreen":    { "enabled": true, "allow": ["critical"] },
  "other_audio":   { "enabled": true, "allow": ["critical"] }
}
```

`allow` lists the priorities that still speak **through** a closed gate.
Valid: `"critical"`, `"normal"`, `"ambient"`, `"debug"`.

| You want | Change |
|---|---|
| Music is *wanted* as background; keep talking over it | `"other_audio": { "enabled": true, "allow": ["critical", "normal"] }` |
| Nothing at all during a video, not even a blocked agent | `"fullscreen": { "enabled": true, "allow": [] }` |
| Stop gating on audio entirely | `"other_audio": { "enabled": false, "allow": [] }` |

All three gates **fail open** — if the probe errors, speech proceeds. That's
deliberate: a broken probe should not silently mute the system. It also means a
gate that never fires looks identical to a gate that is broken, so if you
suspect one, check for the drop rather than assuming:

```bash
prometheus transcript -n 60 -v | grep gate_
```

> `fullscreen` means Hyprland `fullscreen >= 2` — genuinely fullscreen.
> **Maximized is not fullscreen**, on purpose: a maximized editor is normal
> work, and gating on it would mute the system all day.

An intent marked `user_initiated` (the read-aloud keys) skips all three gates.
The **mic gate is never skipped** — pressing a key doesn't make it safe to
speak into a dictation transcript.

### 6.4 — Which apps exist at all

```jsonc
"hypr": {
  "debounce_secs": 1.5,
  "workspace_settle_secs": 2.0,
  "app_names": {
    "brave-browser": "Brave",
    "foot": "the terminal",
    "org.omarchy.agent": "Claude Code",
    "discord": "Discord"
  }
}
```

This map **is** the allowlist (docs/01: "allowlist, not denylist"). A window
class with no entry here is never journaled, never scored, never narrated.

- **"Stop mentioning Discord"** → delete the `"discord"` line. Complete and
  permanent.
- **"It never mentions X"** → add a line. Find the class with
  `prometheus log --hypr | grep unknown_class` while focusing the window.
- The value is what it *says*, so write it the way you'd say it —
  `"foot": "the terminal"`, not `"foot": "foot"`.

| Key | Default | Effect |
|---|---|---|
| `hypr.debounce_secs` | `1.5` | Quiet time after a focus change before journaling. Alt-tabbing to hunt for a window should produce one entry for where you landed. |
| `hypr.workspace_settle_secs` | `2.0` | Same, for workspace switches. Median real gap between them is 1.4 s; 54 % arrive within two seconds of the one before. |

### 6.5 — Rate limits

```jsonc
"limits": {
  "max_words_unprompted": 15,
  "max_words_summary": 30,
  "max_utterances_per_minute": 4,
  "dedup_window_secs": 30,
  "per_category": { "manual": 60, "read-cursor": 60, "terminal-live": 240 }
}
```

Categories in use: `hypr` (desktop), `claude`, `shell`, `manual`
(`prometheus say`), `read-cursor`, `terminal-live`. Any category without an
entry in `per_category` gets `max_utterances_per_minute`. `critical` is exempt
from all of it.

`max_words_unprompted: 15` is the governing number of
[06](06-voice-and-tone.md): piper at `length_scale 0.7` speaks ~4 words/second,
so 15 words is under four seconds and 40 words is a ten-second monologue.

### 6.6 — When Claude and the shell speak

```jsonc
"speak": {
  "claude_blocked":    { "enabled": true,  "priority": "critical" },
  "claude_finished":   { "enabled": true,  "priority": "normal",
                         "min_turn_secs": 45, "short_circuit_words": 25 },
  "command_failed":    { "enabled": true,  "priority": "normal",
                         "min_duration_secs": 10 },
  "command_succeeded": { "enabled": false, "min_duration_secs": 30 }
}
```

| Key | Default | Effect |
|---|---|---|
| `claude_blocked.priority` | `critical` | Exempt from gates, rate limits and verbosity. Leave it. |
| `claude_finished.min_turn_secs` | `45` | Don't speak after turns shorter than this — you were plainly still watching. `0` = every turn. See [§8.3](#83--the-claude-turn-threshold). |
| `claude_finished.short_circuit_words` | `25` | Replies shorter than this are spoken as-is instead of being summarised by the LLM. |
| `command_failed.min_duration_secs` | `10` | A command that failed in under ten seconds failed while you were watching. |
| `command_succeeded.enabled` | `false` | Off by design — docs/06 principle 6, don't narrate the obvious. Set `true` with a `min_duration_secs` of 30–60 if you run long builds. |

### 6.7 — Voice and register

```jsonc
"register": "neutral",          // terse | neutral | warm
"voice": {
  "system": { "model": "en_GB-alan-medium", "length_scale": 0.7 },   // LOCKED
  "agent":  { "model": "en_GB-alba-medium", "length_scale": 0.7,
              "enabled": false },
  "category_map": { "claude": "agent" }
}
```

`register` is the coarse personality dial. Change the word, then:

```bash
prometheus regenerate           # ~15 min of GPU, nothing waiting on it
```

- **`terse`** — "Build failed. Two errors."
- **`neutral`** *(current)* — "The build failed with two errors in the parser."
- **`warm`** — "Build's unhappy — a couple of errors in the parser." *Less
  clipped, never cheerful.*

**Don't change `voice.system`.** It's marked locked because it's settled, and
drifting it costs you the thing that makes this feel like one system.

`voice.agent.enabled: true` gives Claude its own voice — see
[§9.2](#92--the-second-voice).

### 6.8 — The two prose files — the real personality dial

```
~/.config/prometheus/persona.md      who it is, how it speaks
~/.config/prometheus/about-me.md     who you are, what you want to hear
```

These are pasted **verbatim** into every model prompt and into phrase-bank
generation, so editing them *is* configuring it. Add a line to `about-me.md`:

> - Never mention the browser. I don't care what it's doing.

...and after regeneration it is simply true of every phrasing it writes. This
is the most powerful and least mechanical control in the system, and the one
most worth actually using.

Editing either file marks the bank stale; with `phrasebank.auto_regenerate:
true` it regenerates in the background and answers from the old bank meanwhile,
rather than making you wait.

### 6.9 — The one thing that needs a restart

Everything in `config.json` is hot-reloaded. The **code** is not:

```bash
systemctl --user restart prometheus-hypr.service   # the listener
systemctl --user restart prometheusd.service       # the broker
prometheus off && prometheus on                    # both   ⚠ speaks a confirmation
```

Restarting the listener is not amnesia — it re-seeds today's app history from
the journal on startup, which is what stops a toggle producing a burst of
*"Brave, first time today"* about apps you've used since breakfast. You'll see
it in the log as `narrate.seeded events=113`.

---

## 7 — Changing what it says

Three files, and only two of them are yours:

| File | What it is | Edit it? |
|---|---|---|
| `~/.config/prometheus/phrasebank-spec.json` | **The source.** 17 moments, 134 hand-written seeds. | **Yes — this is the one.** |
| `~/.local/state/prometheus/phrasebank.json` | The generated bank (278 phrasings). Build output. | Works, and is **silently lost** at the next regeneration. |
| `~/.local/state/prometheus/phrasebank-vetoed.json` | Lines you cut by ear. Never re-banked. | Managed by `veto`. |

### 7.1 — The two commands you'll actually use

```bash
# Cut a line you never want to hear again. Gone now, and gone from every
# future regeneration.
prometheus-phrasebank veto app_returned "Claude Code's been left running"

# Write one of your own. Goes into the spec, so regeneration keeps it.
prometheus-phrasebank add app_returned "Back at {app}, then."
prometheus-phrasebank add command_failed "{command}'s in the bin." --force
```

`add` validates against that moment's rules — word ceiling, required
placeholders, no invented detail — and refuses if it objects. **Your ear beats
the validator:** `--force` adds it anyway. `add` also clears any earlier veto on
the same line, so it's how you change your mind.

Both take effect **immediately and permanently** — and as of today's fix,
"immediately" now includes the live desktop narrator ([§1](#1--is-anything-left-to-build)).

### 7.2 — Reading what it has to say

```bash
prometheus phrase --show                              # all 17 moments, with counts
prometheus phrase --show app_odd_hour                 # every phrasing for one
prometheus phrase app_opened --slot app=Brave -n 5    # draw five, as it would
```

`*` marks a hand-written seed, `·` one the model wrote. **If you find yourself
vetoing mostly `·` lines, the authoring model isn't earning its place** — tell
me and we'll change it. (It's `gemma2:9b`, chosen head-to-head over `qwen3:8b`
on validator yield: 43 % against 18 %.)

### 7.3 — The audit routine — run after *every* regeneration

Not once. Every time. Phase 5 needed six regenerations and each produced a
genuinely **new** family of bad phrasings once the previous one was blocked:

```
1. invented detail          "Files changed, Claude Code."
2. computer-science nouns   "New Brave process launched."
3. personification          "Brave, humming quietly tonight."
4. self-narration           "Lucent is aware Brave is opening."
5. on-screen furniture      "Brave's interface shows itself."
6. polarity                 "Claude processing input on Prometheus."   <- a BLOCKED agent
```

**A validator tightened against what the model did last time tells you nothing
about where it will go next.** The bank is left clean, not converged — expect
the audit to find something most times, and treat that as it working.

```bash
prometheus-phrasebank verify          # the mechanical rules first

# Draw one line per moment exactly as the runtime would. This is what
# surfaced "Lucent is aware Brave is opening." — nothing static caught it.
for m in app_first_today app_returned app_rare app_odd_hour app_opened; do
  printf '%-20s ' "$m"; prometheus phrase $m --slot app=Brave -n 1
done

# Read what it has actually been saying. Three defects were only ever
# visible here, downstream of the speaker, after passing every check above.
prometheus transcript -n 40

# Then listen.  ⚠ MAKES SOUND
experiments/build-phrasebook-audio.py
experiments/phrasebook/play.sh session
```

Look for, in the order the failures actually appeared: detail it cannot know,
computer-science vocabulary, personification, the system naming itself, guesses
about the future, and **outcomes reported backwards.**

---

## 8 — Decisions waiting on you

Four. None of them is work for me; all of them need a few days of listening
first. In priority order.

### 8.1 — The listening pass (task 5.3)

The one part of Phase 5 that is yours by design, and the only task still open.

```bash
cat experiments/phrasebook/INDEX.md       # read first — `*` hand-written, `~` model
experiments/phrasebook/play.sh session    # ⚠ MAKES SOUND — ~50 seconds
```

`session/` is the one that decides anything: a plausible hour of work in the
order it would actually happen. `by-event/` plays one moment's phrasings back
to back, which answers a different question — *do these all sound like the same
system?*

**The question to hold is never "is this a good sentence."** It is:

> **Imagine hearing this particular sentence for the fortieth time.**

Most phrasings that pass on the page fail that test. Cut what fails with
`prometheus-phrasebank veto <moment> "<the words>"`.

This is worth doing properly because **three of the six defect families above
were only findable downstream of the speaker** — they passed every static check
the validator has. `"Claudes awaits your response."` is invisible on the page
and unmistakable out loud.

### 8.2 — Is it too quiet?

**The most likely thing you'll conclude after two days**, and the fix is not
the dial you'd reach for.

`attention.require_reason` currently includes `"focus"`, which means a focus
change with nothing notable about it stays silent. Measured over 7.8 hours of
real journal:

| `require_reason` | Utterances/hour | Carrying a reason |
|---|---|---|
| `["focus", "workspace", "fullscreen"]` *(current)* | **1.2** | **100 %** |
| `["workspace", "fullscreen"]` | **4.1** | 59 % |

```jsonc
"attention": {
  "require_reason": ["workspace", "fullscreen"]     // drop "focus" -> 3x more speech
}
```

I defaulted this conservative, and I want to be straight about why: **that is a
taste judgement wearing evidence's clothes.** The measurement tells you the two
numbers; it does not tell you which you'd rather live with. Only two days of
listening does.

Note it is *not* `target_rate` you want here. `target_rate` changes the ratio
among eligible events; `require_reason` changes what's eligible at all.

### 8.3 — The Claude turn threshold

`speak.claude_finished.min_turn_secs: 45`, measured from 154 real turns across
59 of this machine's transcripts:

```
p25 15s  |  p50 52s  |  p75 164s  |  p90 455s
at 30s it speaks after 63% of turns
at 45s                  53%    <- current
at 60s                  46%
```

Every Stop now logs `turn_secs` **regardless of the threshold**, so after two
days you can answer this from your own data rather than mine:

```bash
prometheus log | grep -o 'turn_secs[^,}]*' | sort -t: -k2 -n | tail -20
```

Raise toward 60–90 if it still speaks when you hadn't looked away. Drop to `0`
to hear every turn.

### 8.4 — Register

Leave it at `neutral` for now. If after a week everything feels a touch
verbose, try `"terse"` and `prometheus regenerate`. My recommendation from
[06](06-voice-and-tone.md) stands — neutral trending terse, because warm is
delightful for ten minutes and can grate by day three, and personality in
something that speaks unprompted risks becoming a tic.

---

## 9 — Where this could go next

Ordered by value per unit of work, on what I know today. None of it is
committed to; Phase 6 is explicitly "only if earned".

### 9.1 — `battery_low` has 16 phrasings and no producer ⚠

**The clearest gap in the system, and the smallest.** The moment exists in the
spec, the bank holds 16 phrasings for it, `experiments/phrasebook` renders
audio for it — and **nothing in the codebase ever emits it.** This machine has
a `BAT0`. So the system currently cannot tell you the one thing about your
laptop that has a deadline attached.

It's small: watch `/sys/class/power_supply/BAT0/capacity` on the existing udev
or a threshold check in the boot unit, submit one `critical` intent per
crossing with a dedup key. An hour, maybe less. **My recommendation for the
first thing to build after the trial.**

### 9.2 — The second voice

`voice.agent.enabled: true` gives Claude its own voice (`en_GB-alba-medium`,
already mapped via `category_map`). Cheap, possibly clarifying: you'd know
whether it's the system or the agent talking before the first word lands.

Audition first, don't just switch it on:

```bash
prometheus audition --list
prometheus audition --fetch        # ⚠ MAKES SOUND
```

**The cost is memory, and it's tight.** The live system measures 151.1 MB
against a 150 MB single-voice budget already; a second resident piper puts it
near **245 MB against the 250 MB two-voice budget**. Not a problem on this
machine — it's 0.5 % of RAM — but it is not free headroom either.

### 9.3 — Notification interception

`dunst` / `mako` → spoken alerts. This is the largest *unexplored* source of
things worth saying, and the one most likely to be immediately useful, because
notifications are already a curated list of things someone thought you should
know. The risk is equally clear: it is also the largest source of noise on the
machine, and it would arrive with no interest scoring of its own. Would need
its own allowlist, built the way `app_names` was.

### 9.4 — Per-app narration rules

"Never say anything about Brave, but tell me everything about Kdenlive." The
allowlist is currently binary. This is a natural extension of the
`app_names` map — values become objects rather than strings — and it's the
thing you're most likely to *want* after a fortnight, once one particular app
turns out to be the noisy one.

### 9.5 — Two-way conversation

The big one from Phase 6: voxtype → LLM → spoken answer. "What's my disk
usage?" Everything needed is already resident — the mic gate proves voxtype
integration works, the broker handles the speech, `prometheus-llm` handles the
model. It's the most interesting and the least *necessary*, which is exactly
why it was deferred.

### 9.6 — Smaller things worth noting

- **`prometheus brief` is under-used.** `SUPER + ALT + B` is the pull path, and
  it's the part of the system with no cost at all — it speaks only because you
  asked. If two days go by and you never press it, that's worth knowing too.
- **Voxtype's `[output.post_process]` hook** — LLM cleanup of dictation, using
  the model that's already loaded.
- **A `prometheus why` command** — "why didn't you tell me about X?" answered
  from the journal and transcript directly, rather than by reading `-v` output.
  A convenience over machinery that already exists.

---

## 10 — Quick reference

### Keys

| | |
|---|---|
| `SUPER + ALT + N` | **Note this moment** — the only one to memorise |
| `SUPER + ALT + X` | Shut up (cuts mid-word, disables nothing) |
| `SUPER + ALT + P` | Power toggle (zero processes when off) |
| `SUPER + ALT + V` | Verbosity: quiet → normal → chatty |
| `SUPER + ALT + B` | Brief me |

### Commands

```bash
prometheus status                     # processes, RSS, is it alive
prometheus status --speaking          # one word; exit 0 speaking, 1 idle, 2 unknown
prometheus transcript -n 40 -v        # said AND dropped, with reasons
prometheus journal -n 40              # what the desktop did
prometheus feedback --list            # your notes, with evidence
prometheus log --hypr                 # scoring and narration decisions
prometheus phrase --show              # what it has to say
prometheus-phrasebank veto <moment> "<words>"    # cut a line, permanently
prometheus-phrasebank add <moment> "<words>"     # write one, permanently
prometheus regenerate                 # rewrite the bank (~15 min GPU)
prometheus say "text"                 # make it speak something
prometheus stop                       # shut up, from a terminal
```

### Health checks

```bash
experiments/replay-scoring.py            # what would have been spoken
experiments/run-acceptance.sh            # every Phase 0 criterion, re-measured
experiments/test-phrasebank.py           # the runtime guarantees
prometheus-phrasebank verify             # every phrasing still valid
experiments/measure-overhead.sh          # ⚠ speaks — the resource contract
```

### Files

```
~/.config/prometheus/
├── config.json             every number and switch — hot-reloaded, no restart
├── persona.md              who it is                  } regenerate after
├── about-me.md             who you are                } editing either
└── phrasebank-spec.json    the 17 moments and your own phrasings

~/.local/state/prometheus/
├── enabled, verbosity      live state, written by the keys
├── phrasebank.json         generated bank — build output, not source
├── phrasebank-vetoed.json  lines you cut by ear, permanently
├── attention-gain.json     the rate controller's learned gain (delete to reset)
├── feedback.jsonl          your notes, with evidence attached
├── transcript.jsonl        everything said — and dropped, with reasons
├── journal                 what the desktop did
└── *.log                   per-component reasoning, JSONL
```

Config and state are left alone by `./install.sh --uninstall`, so none of your
tuning is at risk from a reinstall.

### Five rules

1. **Press `SUPER + ALT + N` when it annoys you.** Everything else is optional.
2. **One dial at a time, then a day.** Three changes teach you nothing.
3. **Tune from evidence, not memory** — `feedback --list`, `transcript -v`,
   `replay-scoring.py` all exist so you don't have to remember.
4. **Never make phrasings repetitive to make them ignorable.** Turn the rate
   down instead.
5. **Protect "carried a reason."** If it drops below ~90 %, the system has
   stopped selecting for interest even if the volume feels right.
