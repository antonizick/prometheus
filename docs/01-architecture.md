# 01 — Architecture

## The one rule

**Exactly one process opens the audio device.**

Every other component is a *producer* that submits a speech intent over a Unix
socket and forgets about it. Producers never call Piper, never touch `paplay`,
never check whether something else is speaking.

This is the load-bearing decision of the whole design. The failure mode of every
naive "talking computer" — and of the current `omarchy-tts-*` scripts, which each
spawn their own Piper — is two voices talking over each other. Centralizing the
audio device makes overlap *structurally impossible* rather than something we
have to remember to prevent.

---

## Component map

```
 PRODUCERS                         BROKER                      OUTPUT
 ─────────                         ──────                      ──────

 ┌──────────────────┐
 │ prometheus-hypr  │  Hyprland .socket2.sock
 │  window/ws events│  → filter → template
 └────────┬─────────┘
          │
 ┌────────┴─────────┐
 │ prometheus-shell │  bash hooks
 │  cmd + exit code │  → optional summarize
 └────────┬─────────┘
          │  JSON speech intents      ┌───────────────────┐
 ┌────────┴─────────┐   over          │   prometheusd     │    ┌──────────┐
 │ prometheus-claude│  ──────────────▶│                   │───▶│  piper   │
 │  Stop / Notify   │   $XDG_RUNTIME_ │  • priority queue │    │ (warm,   │
 │  hooks           │   DIR/prometheus│  • dedup          │    │  json-in)│
 └────────┬─────────┘   /sock         │  • rate limit     │    └────┬─────┘
          │                           │  • mute gate      │         │ raw PCM
 ┌────────┴─────────┐                 │  • preemption     │         ▼
 │  prometheus say  │                 │  • owns audio     │    ┌──────────┐
 │  (manual / CLI)  │                 └─────────┬─────────┘    │  paplay  │
 └──────────────────┘                           │              └──────────┘
                                                │ consults
                     ┌──────────────────────────┼──────────────────────┐
                     ▼                          ▼                      ▼
          ~/.local/state/prometheus/   $XDG_RUNTIME_DIR/        ollama (localhost)
              enabled, verbosity        voxtype/state            summarizer model
              ── survives reboot ──     ── mic gate ──           ── on demand ──
```

---

## `prometheusd` — the speech broker

A single long-lived user-session daemon. The only component that must be
rock-solid; everything else can crash without taking the voice down.

### Responsibilities

**Owns the warm Piper processes.** Spawns Piper with `--json-input --output_raw`
and keeps it resident, piping raw PCM into a persistent `paplay`. This removes
the 0.3 s per-utterance startup measured in [02](02-system-inventory.md) and
drops time-to-first-sound below ~100 ms. If Piper dies, respawn it with backoff.

**Two voices, one device.** When `voice.agent.enabled` is set, a second Piper
instance runs with a different voice model, used for Claude Code output. The
`category` field on each intent selects the voice. They still share the single
queue and the single audio device — the one-voice-at-a-time rule is about
*simultaneity*, not about there being only one timbre. Cost is a second resident
model (~100 MB RAM, no VRAM); it can be turned off in config, in which case the
second instance is never spawned.

**Runs a priority queue.** Not FIFO. Four levels:

| Priority | Meaning | Behavior |
|---|---|---|
| `critical` | Needs a human now ("Claude is waiting for permission") | Preempts whatever is speaking |
| `normal` | Results worth hearing ("Build passed") | Queued in order |
| `ambient` | Desktop chatter ("Brave.") | Dropped if anything else is queued |
| `debug` | Development only | Only spoken at max verbosity |

Ambient speech being *droppable* is essential. If you alt-tab through six windows
while a build summary is speaking, you want to hear the summary — not six window
names and then the summary.

**Deduplicates.** Every intent may carry a `dedup_key`. An intent whose key
matches something spoken in the last N seconds is silently discarded. This is
what stops the animated-spinner window title from being read four times a second.

**Rate limits.** A hard ceiling on utterances per minute per category. When
exceeded, ambient speech is dropped, not backlogged — stale narration is worse
than silence. Never let a queue grow faster than 4 words/second can drain it.

**Expires stale intents.** Intents carry a TTL. "Opened Brave" is worthless eight
seconds later; it's dropped rather than spoken late.

**Gates on the microphone.** Watches `$XDG_RUNTIME_DIR/voxtype/state`. On
`recording`: stop speaking immediately and hold the queue. On return to `idle`:
resume. This prevents Piper's output being transcribed as dictation, and it means
talking to the machine always takes precedence over the machine talking to you.

**Gates on the toggle.** Reads `~/.local/state/prometheus/enabled`. Disabled means
intents are accepted and dropped — producers never need to know or care.

**Gates on other conditions** (Phase 5): screen locked, fullscreen/presentation,
other audio playing, do-not-disturb.

### Socket contract

`$XDG_RUNTIME_DIR/prometheus/sock` — one JSON object per line, fire-and-forget.
No response, no blocking. A producer writing to a dead socket fails silently and
carries on.

```jsonc
{
  "text":      "Build passed. Two warnings in the parser.",  // required
  "priority":  "normal",        // critical | normal | ambient | debug
  "category":  "shell",         // hypr | shell | claude | manual
                                //   — drives rate limits, mute rules, AND voice choice
  "dedup_key": "build:myproj",  // optional; suppress repeats
  "ttl_ms":    15000,           // optional; drop if not spoken in time
  "preempt":   false            // optional; cut off current speech
}
```

Deliberately dumb. A producer is one `jq -n | socat` away from working, in any
language, with no library.

### Lifecycle

A systemd **user** unit, `WantedBy=default.target`, `Restart=on-failure`.
`systemctl --user enable` makes it start at every graphical login — which is
what makes the toggle survive reboots without any extra machinery.

---

## The sticky toggle

The requirement is a keyboard-toggled persistent on/off that survives reboots.
This is the easiest part of the whole project, and it's worth saying plainly:

**State lives in a file. A file is already persistent.**

```
~/.local/state/prometheus/
├── enabled        # "1" or "0"
└── verbosity      # "quiet" | "normal" | "chatty"
```

- `prometheus-toggle` flips `enabled`, then speaks a one-word confirmation
  ("Listening." / "Quiet.") so there's audible feedback about which state you
  just entered.
- The daemon `inotify`-watches the file — no polling, no restart needed.
- On boot, the daemon starts and reads the file. Whatever it said before the
  reboot, it says now.

Proposed bindings (in `bindings.lua`, matching the existing `o.bind` style):

| Keys | Action |
|---|---|
| `SUPER + SHIFT + S` | Toggle Prometheus on/off (sticky) |
| `SUPER + SHIFT + X` | Shut up — flush queue, stop current utterance, stay enabled |
| `SUPER + SHIFT + ALT + S` | Cycle verbosity quiet → normal → chatty |

`SUPER + SHIFT + X` matters more than it looks. A barge-in / "stop talking" key
that doesn't disable the system is the difference between a tool you trust and
one you turn off permanently the first time it says something long and useless.
It must be instant and unconditional.

*(Key choices need checking against existing Omarchy defaults —
`omarchy menu keybindings --print`. `SUPER+SHIFT+S` may collide with screenshot
bindings; see the commented-out MX Keys line in `bindings.lua`.)*

### The toggle is a power switch, not a mute switch

A hard requirement: **when Prometheus is off, it must cost nothing.** Not "a
small amount." Nothing.

So the toggle does not set a flag that a running daemon consults and ignores.
It **stops the processes**:

```
prometheus-toggle off  →  systemctl --user stop prometheus.target
                          ollama stop <model>          # frees VRAM immediately
                          → zero Prometheus processes remain
```

The persisted state is just a file on disk, and a file costs nothing to exist.
The keybind itself is a Hyprland binding that launches a script — it needs no
resident process to work. So "off" is genuinely, measurably zero: no daemon, no
listener, no Piper, no model, no VRAM, no wakeups. Full details and the
measurement plan are in [07-resource-profile.md](07-resource-profile.md).

The corollary is that the LLM must **not** be pinned resident even when
Prometheus is on. See the three-state model in [07](07-resource-profile.md):
on-and-idle holds ~100 MB of RAM and **zero VRAM**; the model loads on demand
and unloads itself after an idle timeout.

---

## Pull, not only push

One recommendation that goes beyond the original framing, and I think it's the
most important idea in this document after the single-broker rule.

A system that *only* pushes narration at you has a hard ceiling on how useful it
can be, because every utterance is an interruption you didn't ask for. The
annoyance budget gets spent on low-value events, and then the system gets turned
off for good.

So: **push only what can't wait, and let everything else be pulled.**

| | |
|---|---|
| **Push** (spoken unprompted) | Agent blocked waiting on you. A long command failed. That's nearly the whole list. |
| **Pull** (spoken on request) | Everything else — on a keypress, when *you* have the attention to spend. |

`SUPER + SHIFT + B` — **brief me.** Summarizes what's happened since the last
briefing: commands run and how they ended, agent sessions that finished and what
they did, windows opened. One paragraph, spoken, on demand.

This inverts the economics. Instead of twenty interruptions of which two mattered,
you get silence plus a five-second summary whenever you look up from something
else. It also makes the local LLM far more valuable: briefing a batch of events
is a task where a small model does genuinely well, and it runs once per request
rather than once per event — which fits the on-demand model-loading design
perfectly.

The event journal that makes this possible (`~/.local/state/prometheus/journal`,
an append-only JSONL of everything the daemon saw, spoken or not) is cheap to
write and independently useful for tuning what *should* be spoken.

**Recommendation: build the pull path first (Phase 1), and add push narration
sparingly afterward, driven by what the journal shows is actually worth saying.**

---

## `prometheus-hypr` — ambient narrator

Reads the Hyprland event socket and turns a subset of events into short phrases.

**No LLM call at event time, ever.** These fire constantly and must be instant.
An LLM inference here would add a second of latency to every window focus change
and hold the model in VRAM all day, breaking
[07-resource-profile.md](07-resource-profile.md).

But the phrasing is still **LLM-written and never repeats** — because it's
generated ahead of time, in batches, into a phrase bank. At event time this is a
dictionary lookup and a weighted random choice: under 5 ms, zero VRAM. See
[08-personality-and-config.md](08-personality-and-config.md).

Pipeline:
```
read event → parse → interest score → probability gate (~15%)
           → debounce → pick unused phrasing from bank → emit
```

The **interest score** is what makes the ~15 % firing rate feel considered rather
than random — novelty, rarity, odd hours and returns-after-absence raise it;
recent speech, repetition and rapid alt-tabbing suppress it. Details and weights
in [08](08-personality-and-config.md).

The filter is still the component. Rules that fall directly out of the live event
capture in [00-feasibility](00-feasibility.md):

- **Ignore `windowtitle` churn entirely by default.** Titles change on every
  spinner frame, every tab switch, every progress update.
- **Debounce focus changes** (~1.5 s). Alt-tabbing through windows to find one
  should produce silence, then the name of where you landed.
- **Allowlist, not denylist.** Only narrate app classes we've deliberately added.
  An unknown app says nothing rather than reading a raw class string like
  `org.omarchy.agent` aloud.
- **Never narrate Prometheus's own activity.**
- **Say the friendly name.** `brave-browser` → "Brave".

Verbosity tiers control breadth:
- `quiet` — workspace switches only
- `normal` — + app launches and closes
- `chatty` — + focus changes, fullscreen, monitor changes

---

## `prometheus-shell` — terminal result narrator

Two modes, because reliable output capture in a plain terminal is genuinely
awkward (see [05-risks](05-risks-and-open-questions.md) Q2).

**Mode A — exit-code narration (default, always on).** A bash `PROMPT_COMMAND`
hook notes the command and its exit status. No output capture, no LLM, no cost.

Even this is useful: it only speaks when a *long* command finishes (> ~10 s, so
you've likely looked away) or when a command *fails*. Silence for the fast
successes.

> "npm build failed after forty seconds. Exit code one."

**Mode B — summarized output (opt-in per command).** Prefix a command with `pr`:

```bash
pr make test
```

The wrapper tees output to a temp file, and on completion hands the tail to the
local LLM for a two-sentence spoken summary. Explicit opt-in means you choose
which commands are worth narrating, and it sidesteps the whole problem of
capturing output from an interactive TUI.

> "All forty-seven tests passed in twelve seconds. Nothing to look at."

---

## `prometheus-claude` — agent session narrator

Claude Code hooks in `~/.claude/settings.json`. The cleanest data source in the
project: structured JSON, already on disk, zero API cost.

| Hook | Priority | Purpose |
|---|---|---|
| `Stop` | `normal` | Claude finished — summarize what it did |
| `Notification` | **`critical`** | Claude is *blocked waiting for you* |
| `SessionEnd` | `ambient` | Optional bookend |

`Notification` is the highest-value event in the entire project. The thing that
actually wastes your time is a long agent run that stopped ten minutes ago to ask
a yes/no question while you were looking elsewhere. That one deserves preemption.

The `Stop` path receives a transcript path, reads the final assistant message,
and routes it:

- Message already short (< ~25 words) → speak a lightly-cleaned version directly,
  no LLM at all. Fastest and most faithful path; likely covers many turns.
- Longer → local LLM, hard-capped at two sentences.
- Either way, strip code blocks, file paths, and markdown — they're unspeakable.
  "Modified src/auth/middleware.ts" should become "changed the auth middleware."

**Cost: zero tokens.** We summarize a file that has already been written to disk.

---

## `prometheus-llm` — summarizer

A thin wrapper over Ollama's local HTTP API. See
[03-model-selection.md](03-model-selection.md) for which model.

Non-negotiable constraints:

- **Two sentences. Hard cap via `num_predict`.** At 4 words/second, 40 words is
  a ten-second monologue. The system prompt says so and the token limit enforces
  it regardless.
- **Written for the ear, not the eye.** No lists, no paths, no identifiers, no
  markdown. "Three tests failed in the parser" — not
  "3 failures: test_parse_a, test_parse_b, test_parse_c".
- **Timeout ~4 s, fail silent.** A summary that arrives after you've moved on is
  worse than no summary. If the model is slow, say nothing.
- **Model is loaded on demand and unloads itself.** `OLLAMA_KEEP_ALIVE` set to a
  few minutes — *not* `-1`. Holding 3–5 GB of VRAM permanently on an 8 GB card
  to save 2 seconds on an occasional summary is a bad trade. See
  [07-resource-profile.md](07-resource-profile.md).
- **Never blocks a producer.** Summarize, then emit; the hook returns immediately.
- **Ollama's own service is socket-activated or stopped with the toggle**, so an
  idle Ollama daemon isn't sitting resident either.

---

## Failure behavior

Every failure mode degrades to **silence**, never to noise or a blocked desktop.

| Failure | Result |
|---|---|
| Daemon down | Producers' socket writes fail silently; desktop unaffected |
| Piper crashes | Daemon respawns with backoff; queue held briefly |
| Ollama down / slow | Summaries skipped; template narration continues |
| Model returns garbage | Length cap truncates; worst case one odd sentence |
| Producer crashes | Other producers unaffected |
| Audio device busy | Utterance dropped, not queued forever |

The desktop must never wait on this system. Nothing in Prometheus is allowed to
block a keystroke, a shell prompt, or a Claude Code turn.
