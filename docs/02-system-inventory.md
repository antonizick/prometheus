# 02 — System Inventory

Measured on 2026-09-11. Everything here was verified by running a command, not
assumed. Re-verify after any major Omarchy update.

## Hardware

| | |
|---|---|
| CPU | Intel Core i7-9750H @ 2.60 GHz — 6 cores / 12 threads |
| RAM | 31 GiB total, ~16 GiB free, ~25 GiB available |
| Swap | 62 GiB |
| GPU | **NVIDIA GeForce RTX 2070 with Max-Q Design — 8192 MiB VRAM** |
| NVIDIA driver | 610.57.04 (`nvidia-smi` functional) |
| Disk | 930 GB LUKS-mapped root, 864 GB free |
| Audio | PipeWire 1.6.8 (PulseAudio compat layer) |
| Default sink | `alsa_output.pci-0000_00_1f.3-platform-skl_hda_dsp_generic.HiFi__Speaker__sink` |

**Implication:** 8 GB VRAM comfortably hosts a 3B–8B quantized model kept
permanently resident. No GPU upgrade needed, no CPU-only fallback needed.

## OS and desktop

| | |
|---|---|
| Kernel | Linux 7.2.3-arch1-3 |
| Desktop | Omarchy / Hyprland |
| Config style | **Lua** (`~/.config/hypr/*.lua`) — not the older `.conf` syntax |
| Shell | bash (`~/.bashrc`) |
| AUR helper | `yay` present (not needed — everything is in official repos) |

### Hyprland config files
```
~/.config/hypr/
├── autostart.lua     ← a11y bus setup + NX-protocol PATH shim live here
├── bindings.lua      ← existing TTS keybinds live here
├── hyprland.lua
├── input.lua
├── looknfeel.lua
├── monitors.lua
├── hyprsunset.conf
└── xdph.conf
```

**Note the Lua config style.** Bindings are added with
`o.bind("KEYS", "Description", "command")` and unbound with `hl.unbind("KEYS")`.
Prometheus keybinds must follow this form. `autostart.lua` already uses both
`o.exec_on_start` and `hl.env`, so there's precedent for what we need.

## Existing audio / speech stack

### Piper TTS — **do not change any of this**
| | |
|---|---|
| Binary | `/opt/piper-tts/piper` (2.8 MB, from `piper-tts-bin`) |
| espeak data | `/opt/piper-tts/espeak-ng-data` |
| Voice model | `~/.local/share/piper/voices/en_GB-alan-medium.onnx` (63 MB) |
| **Length scale** | **`0.7`** — ~30 % faster than default. Locked. |
| Output rate | 22050 Hz mono |

Relevant CLI flags confirmed present on this build:
- `--json-input` — line-delimited JSON on stdin → **enables a resident daemon**
- `--output_raw` — streams audio as produced → **enables early playback**
- `--sentence_silence NUM` — default 0.2 s, tunable for pacing
- `--noise_scale` / `--noise_w` — leave at defaults; voice character is locked

#### Measured synthesis performance
| Utterance | Synth time | Audio length | RTF |
|---|---|---|---|
| "Opened Brave browser." (3 words) | 0.30–0.32 s | ~1.45 s | ~0.21 |
| 40-word summary | 0.715–0.716 s | ~9.8 s | ~0.073 |

**Speaking rate at `length_scale 0.7`: roughly 4 words/second.**
This is the single most important number in the project — it's the budget that
forces brevity. A 40-word summary is a **ten-second** monologue.

### Voxtype (speech-to-text) — already working
| | |
|---|---|
| Binary | `/usr/bin/voxtype` |
| Service | `voxtype.service` (user unit, active/running) |
| Config | `~/.config/voxtype/config.toml` |
| Whisper model | `base.en` |
| Mode | Push-to-talk, hotkey bound in Hyprland |
| Output | Types at cursor via ydotool; clipboard fallback |
| **State file** | **`$XDG_RUNTIME_DIR/voxtype/state`** → `idle` \| `recording` \| `transcribing` |

**The state file is the key integration point.** It lets Prometheus know when
the microphone is live and stop talking into it. Without this, Piper's output
gets transcribed back as dictation — the feedback loop that would otherwise sink
this project. Verified present and readable; currently reads `idle`.

Voxtype also has an unused `[output.post_process]` hook that can pipe
transcriptions through an arbitrary command — currently just a `sed`. Worth
remembering as a future integration point, out of scope for now.

### Existing TTS scripts (to be left alone)
```
~/.local/bin/omarchy-tts-read-cursor         # SUPER+SHIFT+R
~/.local/bin/omarchy-tts-terminal-live       # SUPER+SHIFT+L / +ALT+L
~/.local/share/tts-read-cursor/text_at_point.py
~/.local/share/tts-read-cursor/terminal_feed.py
~/.local/state/tts-read-cursor/{pid,live/}
```
These call Piper directly. Once the broker exists they should be migrated to
route through it (see [04-build-plan.md](04-build-plan.md), Phase 5) so there is
only ever one thing holding the audio device.

## Claude Code

| | |
|---|---|
| Settings | `~/.claude/settings.json` — currently only `tui`, `theme`, `model`. **No `hooks` key yet, so no conflict.** |
| Projects dir | `~/.claude/projects/` |
| Sessions | `~/.claude/sessions/`, `~/.claude/history.jsonl` |
| Existing memory | `~/.claude/projects/-home-nick-Work/memory/` |

## Required installs (none yet performed)

| Package | Source | Size | Purpose |
|---|---|---|---|
| `ollama-cuda` | `extra/` — **official repo** | ~1 GB + CUDA deps | Local LLM runtime w/ GPU |
| model weights | ollama registry | ~2–5 GB | Summarizer (see [03](03-model-selection.md)) |

Nothing from the AUR. Nothing built from source. Nothing that needs a Python
virtualenv unless we choose one.

## Tooling already present
`jq`, `socat`, `inotifywait`, `hyprctl`, `grim`, `tesseract`, `paplay`,
`pw-play`, `python3` (3.14), `tmux`, `systemctl`, `yay`, `pacman`.

## Notable absences
| Missing | Matters? |
|---|---|
| `ollama` | Yes — install in Phase 2 |
| `bc`, `/usr/bin/time` | No — used Python for benchmarking instead |
| `uv` | No |
| **tmux not currently running** | **Yes** — the existing live-terminal-read feature *requires* a tmux session and therefore does nothing right now. Directly relevant to how Prometheus captures terminal output. See [05-risks](05-risks-and-open-questions.md) Q2. |
