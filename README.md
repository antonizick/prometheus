# Prometheus

**A voice for the operating system.** A local, keyboard-toggled speech layer for
a Linux desktop that decides *what is worth saying* — and says almost nothing.

No cloud, no API keys, no ongoing cost. Everything runs on the machine it talks
about.

> **Status:** Phases 0–5 built and measured. The speech broker, event journal,
> briefings, local-LLM summarizer, offline phrase bank, Claude Code hooks,
> shell integration, and — since Phase 5 — **ambient desktop narration**, tuned
> against real journalled history rather than guessed. Context gates (locked
> screen, fullscreen, other audio) and the migrated `omarchy-tts-*` scripts all
> route through the one broker. See [Status](#status).
>
> Phase 5 replayed the narration policy against a real working day before
> switching it on. As designed it would have spoken **14.7 times an hour** with
> fewer than half of those utterances having any reason behind them; it now
> speaks **1.2 times an hour, and every one carries a signal**. Three of the
> five interest signals turned out never to fire against real data. The whole
> argument is in [notes/2026-09-12-phase-5.md](notes/2026-09-12-phase-5.md) and
> is re-runnable with `experiments/replay-scoring.py --compare`.
>
> *(Utterances-per-hour divides by wall-clock time, so a journal containing a
> lot of idle reads quieter — the same configuration measures 0.8/hour over a
> 12-hour window. The stable figures are the ones that describe the policy
> rather than the day: **~16 % achieved against a 15 % target**, and **100 % of
> utterances carrying a reason**, up from 46 %.)*

---

## The idea

Text-to-speech on a desktop is a solved problem, and it is not what this is.
Read-aloud tools narrate *text you point at*. Prometheus watches what the machine
is doing and makes a judgement about whether any of it is worth interrupting you
for. Almost always, the answer is no.

Three kinds of thing it has to say, kept separate because they have wildly
different latency and intelligence requirements:

| | Example | How | Budget |
|---|---|---|---|
| **Ambient** | *"Brave, first time today."* | Pre-generated phrase bank | < 300 ms |
| **Results** | *"Two parser errors killed the build."* | Local LLM | ~2 s |
| **Agent** | *"Claude needs you — Prometheus."* | Hook + phrase bank | instant |

That last one is the reason the project exists. The thing that actually wastes
your time is a long agent run that stopped ten minutes ago to ask a yes/no
question while you were looking elsewhere.

## The hard part isn't the engineering

Getting a computer to talk is easy. Getting one you don't switch off after forty
minutes is the entire problem, and every design decision here is biased toward
saying less:

- **Silence is the default.** The most common output is nothing.
- **Push only what can't wait; let everything else be pulled.** One key
  summarises the last stretch of work, on your schedule rather than the
  machine's.
- **Under fifteen words, outcome first.** Piper at `length_scale 0.7` speaks
  about four words per second — a forty-word summary is a *ten-second monologue*
  you didn't ask for.
- **Never read out what can't be heard.** Paths, hashes, line numbers and code
  are visual objects. Aloud they're noise.

## It never says the same thing twice

The most interesting piece of the design, and the one worth stealing.

A system that cycles through eleven fixed sentences stops feeling like
intelligence almost immediately. But generating phrasing with an LLM *at event
time* is fatal: a second of latency on every window focus change, and 5 GB of
VRAM held all day.

So the two are separated. **Phrasings are LLM-written, but written offline, in
batches, into a bank.** At the moment an event fires, speaking is a dictionary
lookup and a weighted random pick excluding whatever was said recently:

```
   OFFLINE (on demand, ~15 min, GPU busy)      RUNTIME (every event)
   persona.md + about-me.md                    weighted pick from the bank,
   + the moments it has to speak to            excluding the last 15 used
              ↓                                          ↓
   a 9B local model writes candidates          ~10 µs, no model loaded,
              ↓                                  no VRAM, no network
   a validator throws out about half
              ↓
   phrasebank.json
```

Structure stays rigid — outcome first, under the word cap, no paths, no preamble
— so you always know what kind of thing you're hearing from the first word. Only
the words change.

**The validator is the component.** Small local models write the same sentence
forty times with one word swapped, reach for status-report vocabulary the moment
they run out of ideas, and invent detail they cannot possibly know. Real
examples it caught and rejected:

| Rejected | Why |
|---|---|
| *"Scrolling through Brave's tabs."* | It cannot see the screen |
| *"Still waiting on the build."* | For a build that had **failed** |
| *"The build timed out at forty seconds."* | For one that had **succeeded** |
| *"Check the build log."* | An instruction; nobody asked for help |
| *"Something requires input."* | A blocked-agent alert that never says *which* agent |

Everything banked is tagged as hand-written or model-written, every rejection is
logged with its reason, and a phrasing you cut by ear is never re-banked.

## What it costs

Measured on the target machine, not estimated.

| | |
|---|---|
| Time to first sound | **48–93 ms** *(the baseline it replaced: 310 ms)* |
| Phrase lookup at event time | **9–20 µs**, p95 28 µs |
| Shut-up key → silence | **< 20 ms**, mid-word |
| Speech stops after the mic goes live | **< 20 ms** |
| RAM, on and idle | **117 MB** *(217 MB with a second voice)* |
| VRAM, on and idle | **zero** — the model loads on demand and unloads itself |
| CPU and wakeups, on and idle | **zero** |
| Processes when switched off | **zero** |

That last line is a design commitment, not a side effect. The toggle is a power
switch: "off" stops every process and frees VRAM, and it survives a reboot.

`experiments/run-acceptance.sh` re-checks every criterion;
`experiments/measure-overhead.sh` re-measures the resource contract.

## Architecture

```
 producers                    broker                      output
 ─────────                    ──────                      ──────
 prometheus-hypr  ─┐
 Claude Code hooks ─┼─ JSON over a  ──→  prometheusd  ──→  warm Piper ──→ paplay
 shell hooks       ─┤   unix socket      priority queue    (one process
 prometheus say    ─┘                    dedup, TTL         owns the audio
                                         rate limit         device)
                                         mic gate
```

**One queue, one daemon.** Every component emits *speech intents* to a single
broker that owns the audio device; nothing else calls Piper directly. That's the
difference between a conversational OS and a room full of processes shouting.
Producers need no library:

```bash
echo '{"text":"Build passed.","priority":"normal","category":"shell"}' \
  | socat - UNIX-CONNECT:$XDG_RUNTIME_DIR/prometheus/sock
```

Speech is hard-gated on the microphone: the moment dictation starts, it stops
talking mid-word.

## Status

| Phase | | |
|---|---|---|
| 0 | Speech broker, toggle, config, resource contract | ✅ built, 13/13 acceptance |
| 1 | Hyprland event journal, briefings, interest scoring | ✅ built |
| 2 | Local LLM: summarizer, LLM briefings, phrase bank | ✅ built, bank approved by ear |
| 3 | Claude Code integration — `Stop`/`Notification` hooks | ✅ built |
| 4 | Shell integration | ✅ built, not yet heard live |
| 5 | Living with it — tuning from real data | **built** |
| 6 | Two-way conversation | speculative |

**Desktop narration was switched on last, and only after the evidence existed
to aim it.** Phase 1 collected a journal without speaking; Phase 5 spent it.
That ordering paid for itself: replayed against a real day, three of the five
interest signals in the design had *never fired* — `returned` used a
3600-second absence threshold and the longest real gap was 3454 seconds — and
workspace switches, which the architecture made the always-on floor, turned out
to be the most frequent event on the desktop rather than the rarest, absorbing
~90% of all ambient speech.

None of that is visible from the design. All of it is obvious from one day of
`experiments/replay-scoring.py --compare`, which still re-runs the entire
argument against whatever journal exists now.

## Requirements

Built against one specific machine, and honest about it: an Arch-based
[Omarchy](https://omarchy.org) desktop running Hyprland, with an NVIDIA GPU.
Nothing here is portable without work.

- **Python 3.11+**, standard library only — no pip install, no virtualenv
- **Bash 5.0+** for the shell integration (Phase 4) — its command-duration
  timer relies on `$EPOCHREALTIME`
- **[Piper](https://github.com/rhasspy/piper)** at `/opt/piper-tts`, with voices
  in `~/.local/share/piper/voices` (`en_GB-alan-medium` and `en_GB-alba-medium`)
- **PipeWire / PulseAudio** (`paplay`)
- **Hyprland**, for the event socket
- **[Ollama](https://ollama.com)** (`ollama-cuda`) — for Phase 2 onward only.
  `qwen3:4b-instruct` at runtime, `gemma2:9b` for offline phrase authoring.
  Deliberately *not* enabled as an always-on service.
- **systemd user session**

## Getting started

```bash
./install.sh                   # symlinks binaries + units, seeds config

prometheus on                  # power on   (SUPER+ALT+P)
prometheus say "build passed"  # speak something
prometheus status              # what's running and what it costs
prometheus off                 # stops every process, frees VRAM
```

| Keys | Action |
|---|---|
| `SUPER + ALT + P` | Toggle the voice on/off (sticky, survives reboot) |
| `SUPER + ALT + X` | Shut up — flush the queue, cut the current utterance |
| `SUPER + ALT + V` | Cycle verbosity: quiet → normal → chatty |
| `SUPER + ALT + B` | Brief me — what's happened since the last briefing |
| `SUPER + ALT + N` | Note — record a reaction, with the evidence attached |

### Hearing it before you trust it

No phrasing ships on the strength of how it looks in a terminal. The review is a
command, and the audio is generated locally rather than committed:

```bash
experiments/build-phrasebook-audio.py   # renders WAVs + INDEX.md — silent
experiments/phrasebook/play.sh          # ⚠ this one makes sound
```

It stages a plausible hour of work in the order it would happen, and every
phrasing for one moment back to back. The question is never "is this a good
sentence" — it's *"would I still be happy hearing this the fortieth time?"*

## Making it yours

Four files in `~/.config/prometheus/`, hot-reloaded:

```
config.json            numbers and switches — rate, weights, word caps, models
persona.md             who it is, and how it speaks          } regenerate
about-me.md            who you are, and what you want to hear } after editing
phrasebank-spec.json   the moments it speaks to, and your own phrasings
```

Two of those are prose, because personality is a paragraph, not a field. They're
pasted verbatim into every model prompt, so **editing them is configuring it**.
Add a line to `about-me.md` like *"Never mention the browser, I don't care what
it's doing"*, run `prometheus regenerate`, and it will simply be true of
everything it writes from then on.

```bash
prometheus regenerate                                # rewrite the bank from the prose
prometheus phrase --show                             # what it says, and how many ways
prometheus-phrasebank add app_opened "Right, {app}." # write one of your own
prometheus-phrasebank veto app_returned "…"          # cut one, permanently
prometheus feedback "that broke my concentration"    # capture a reaction now
experiments/replay-scoring.py --rate 0.05            # what a change *would* have done
experiments/replay-scoring.py --compare              # this policy vs the one before it
```

**The two dials worth knowing first**, both one line in `config.json`:

```jsonc
"attention": { "require_reason": ["focus", "workspace", "fullscreen"] }
// drop "focus" to hear ~3x as much: 1.2 -> 4.1 utterances/hour, measured

"speak": { "claude_finished": { "min_turn_secs": 45 } }
// 45s speaks after ~53% of turns; 0 speaks after all of them
// `prometheus log | grep turn_secs` shows your own distribution first
```

Speech preferences only surface after living with something, so the tuning path
is a first-class part of the system — [docs/10](docs/10-feedback-and-tuning.md)
is the whole story.

## Documentation

Roughly 21,000 words of it, because most of the decisions here are judgement
calls that are worthless without their reasoning.

| Document | What's in it |
|---|---|
| [00-feasibility.md](docs/00-feasibility.md) | The verdict, with measured evidence |
| [01-architecture.md](docs/01-architecture.md) | Components, data flow, socket contract |
| [02-system-inventory.md](docs/02-system-inventory.md) | Measured facts about the target machine |
| [03-model-selection.md](docs/03-model-selection.md) | Which models, where, and why |
| [04-build-plan.md](docs/04-build-plan.md) | Phases with acceptance criteria |
| [05-risks-and-open-questions.md](docs/05-risks-and-open-questions.md) | What could go wrong; what needs a human's call |
| [06-voice-and-tone.md](docs/06-voice-and-tone.md) | What it says and how it says it |
| [07-resource-profile.md](docs/07-resource-profile.md) | Overhead when off, idle, and working |
| [08-personality-and-config.md](docs/08-personality-and-config.md) | Non-repeating speech; the config and persona files |
| [09-session-and-budget-plan.md](docs/09-session-and-budget-plan.md) | Which model per phase, token discipline |
| [10-feedback-and-tuning.md](docs/10-feedback-and-tuning.md) | How to tell it it's wrong, and fix it |

`decisions/` holds ADRs — one file per hard-to-reverse choice, with the argument
that led to it. `notes/` holds dated session logs, including the things that
didn't work. `experiments/` holds the benchmark harnesses and their raw results.

## Non-goals

- **Not a screen reader.** It doesn't read what's on screen; it decides what's
  worth mentioning.
- **Not an assistant.** It doesn't take commands or answer questions. (Phase 6
  is speculative.)
- **No cloud anything.** No API keys, no telemetry, no network calls beyond
  `127.0.0.1`.
- **Not portable, yet.** It's built against one desktop and says so.

## License

Not yet chosen. Consider it all-rights-reserved until it is.
