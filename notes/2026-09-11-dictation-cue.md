# 2026-09-11 — The missing dictation cue

A side quest during the Phase 0 build. Recorded because most of the work landed
**outside this repo**, in `~/.config/voxtype/` and `~/.config/omarchy/plugins/`,
which is exactly the kind of change that gets forgotten.

## The question

Nick: *"voxtype used to have a visual cue that looked very cool… where did it go?"*

## What was actually wrong — two separate things

**1. The bar indicator was invisible for most of the time it mattered.**

Omarchy's packaged `shell/plugins/bar/indicators/Dictation.qml` sets:

```qml
active: state === "recording"
```

and `BarIndicator` draws an inactive indicator at `opacity: 0` — fully
invisible, not merely dim. So the cue appeared while the key was held and
vanished the instant it was released, through the whole of **transcription**,
which is the part that actually takes time and the part where you're waiting to
know something is happening.

The QML even prepares an hourglass glyph for the transcribing state that stock
can never reach, because `active` is already false by then.

**2. The beeps were off.** `[audio.feedback]` in `~/.config/voxtype/config.toml`
was commented out entirely.

## The thing I got wrong first

I mocked up five candidate cues and offered to build a floating waveform OSD
from scratch in QML. **Voxtype already ships one.** Restarting the service after
the beeps change printed:

```
voxtype_osd_gtk4: voxtype-osd-gtk4 starting;
  socket="/run/user/1000/voxtype/audio.sock" size=400x48 margin=24 pos=BottomCenter
```

A whole `osd.*` config namespace exists — `osd.enabled`, `osd.frontend`
(`gtk4 | native | quickshell`), `osd.layout`, `osd.palette`, `osd.position`,
`osd.waveform_gain`, and more. `voxtype config schema` lists all of it.

Lesson worth keeping: **check what the tool already does before mocking up a
replacement for it.** Twenty minutes of design went into a panel that shipped
with the package. `voxtype config schema` would have found it immediately.

Why it appeared to have "disappeared" was never established — `osd.enabled` was
already `true` and nothing in the config disabled it. If it goes missing again:

```bash
journalctl --user -u voxtype.service | grep -i osd     # is the child starting?
```

## What is actually in place now

| | State |
|---|---|
| Visualizer | **Original gtk4**, bottom-centre live waveform. Briefly switched to the `quickshell` frontend with the Omarchy palette; Nick preferred the original, so every override was **unset** (not overwritten) and it's back on built-in defaults. |
| Beeps | **Off** — Nick prefers the visual cue alone. |
| Bar indicator | **Fixed.** |

The indicator fix, in `~/.config/omarchy/plugins/nick.indicators/` (cloned with
`omarchy plugin clone omarchy.indicators`, so it survives Omarchy updates):

```qml
active: state !== "idle"      // was: state === "recording"
```

It now stays lit through transcription, and finally shows the hourglass glyph
stock prepared but never displayed.

## Files changed outside this repo

```
~/.config/voxtype/config.toml                              audio.feedback.enabled = false
~/.config/voxtype/config.toml.bak.*                        backups, one per edit
~/.config/omarchy/plugins/nick.indicators/                 cloned; Dictation.qml patched
~/.config/omarchy/shell.json                               bar switched to nick.indicators
~/.config/hypr/bindings.lua                                Prometheus keybinds (Phase 0)
~/.config/hypr/bindings.lua.bak.*                          backup
```

Never edit `/usr/share/omarchy/` — it's package-owned and overwritten on update.
Clone with `omarchy plugin clone <id>` instead.

## The one thing this gave Prometheus

The detour produced the first test of the mic gate against the **real** voxtype
state file rather than the fake directory the acceptance suite uses:

```
gate.mic: HELD — microphone is live, stopping speech now  state=recording
intent.interrupted: cut after 1180ms of a 5364ms utterance
```

paplay went 1 → 0. That closes an acceptance criterion that had only been proven
synthetically. See [2026-09-11-phase-0.md](2026-09-11-phase-0.md).

## Not done

Options 3 (screen-edge halo) and 5 (caret chip) from the audit were not built —
Nick chose 2 and 4, and 4 turned out to already exist. The mockups remain
useful if the current cue ever proves insufficient.
