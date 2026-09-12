# 00 — Feasibility Assessment

**Date:** 2026-09-11
**Verdict:** **Yes — feasible, practical, and free to run.**

Not "feasible with caveats about exotic dependencies." Every capability this
needs is already installed and working on this laptop, or is one `pacman -S`
away from an official Arch repository. I verified each one rather than assuming.

---

## The four things that had to be true

A project like this dies on any one of these. All four hold.

### 1. The OS must expose a stream of "something happened" events ✅

Hyprland publishes an event socket. I connected to it live and watched this very
Claude session's window emit events in real time:

```
$ socat -U - UNIX-CONNECT:$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket2.sock

windowtitlev2>>55e47d55eb40,◐ Omarchy conversational OS with Piper TTS
activewindow>>org.omarchy.agent,◐ Omarchy conversational OS with Piper TTS
```

This gives window open/close, focus change, workspace switch, fullscreen,
monitor change — with app class and title attached. It is a clean, push-based
feed. No polling, no screen-scraping, no OCR.

> **It also immediately showed the first real problem.** Look at the title:
> `◐` then `◑` — a spinner animating. A naive narrator would say "Omarchy
> conversational OS" four times a second, forever. Event filtering is not a
> polish task; it is the core of this component. Noted in
> [05-risks](05-risks-and-open-questions.md).

### 2. Piper must be fast enough to feel like speech, not like buffering ✅

Measured on this machine, with the exact voice and `--length_scale 0.7` setting
already in use:

| Utterance | Synthesis wall time | Resulting audio | Real-time factor |
|---|---|---|---|
| "Opened Brave browser." | **0.31 s** | 1.5 s | 0.21 |
| ~40-word summary | **0.72 s** | 9.8 s | 0.073 |

Consistent across repeated runs. That 0.3 s includes process spawn *and* loading
the 63 MB ONNX model every time — so it's a floor that can be lowered, not a
ceiling.

And it can be lowered, because `piper --help` on this build confirms two flags
that matter enormously:

- `--json-input` — reads **line-delimited JSON from stdin**, so one Piper process
  can stay resident and take an unlimited stream of utterances.
- `--output_raw` — emits **raw audio as it becomes available**, so playback can
  start on the first sentence instead of waiting for the whole utterance.

Together these mean a warm Piper daemon with sub-100 ms time-to-first-sound.
That's conversational.

### 3. There must be a clean way to read AI session results — without OCR ✅

This is where the current setup struggles most, and where the biggest improvement
is available.

Claude Code supports **hooks**: shell commands the harness runs on lifecycle
events, configured in `~/.claude/settings.json` (currently a 4-line file — no
conflicts). The relevant ones:

- `Stop` — fires when Claude finishes responding. Receives the **transcript path**
  on stdin as JSON.
- `Notification` — fires when Claude needs input or permission.
- `SessionStart` / `SessionEnd` — session boundaries.

So the result text arrives as **structured data from a file**, not as pixels
scraped off a screenshot and not as a mangled tmux byte stream. No OCR, no ANSI
stripping, no fighting with TUI redraws.

This is a categorically better input than what `omarchy-tts-terminal-live`
currently has to work with, and it's the single strongest technical argument for
building this properly rather than extending the existing scripts.

*(Exact hook payload schema is verified in Phase 3, Task 3.1 before anything is
built on it.)*

### 4. Local AI must be genuinely viable, not a compromise ✅

| Resource | Available |
|---|---|
| GPU | **NVIDIA RTX 2070 Max-Q, 8 GB VRAM**, driver 610.57.04 |
| RAM | 31 GB (16 GB free) + 62 GB swap |
| CPU | i7-9750H, 6c/12t |
| Disk | 864 GB free |
| Package | **`extra/ollama-cuda 0.33.3-1`** — official repo, not AUR |

8 GB of VRAM is comfortably enough for the 3B–8B class of model this needs, with
room to keep it permanently resident so there's no load penalty on first use.

This is a better local-AI machine than most people attempting this have.

---

## Cost analysis

**Ongoing cost: $0.** This is not a qualified "cheap" — it's genuinely zero.

| Component | Cost |
|---|---|
| Piper TTS | Free, local, already installed |
| Hyprland event feed | Free, already running |
| Ollama + model | Free, local, one-time ~3–5 GB disk |
| Speech broker / narrators | Our own code |
| **Anthropic API tokens added** | **Zero** |

That last row deserves emphasis, since it was the stated concern. Summarizing a
Claude Code session costs no API tokens because the `Stop` hook reads the
transcript **from a local file that has already been written to disk** and hands
it to the local model. We are summarizing text we already have. At no point does
Prometheus call a paid API.

The only real costs are ~5 GB of disk and some watts.

---

## What I am confident about vs. what needs proving

**Confident (verified on this machine):** event feed, Piper latency, Piper daemon
mode, hook mechanism exists, hardware headroom, package availability, voxtype
state file for mic coordination.

**Needs proving in the build (and has a fallback if it fails):**

| Uncertainty | Fallback if it disappoints |
|---|---|
| Small-model summary *quality* at 2-sentence length | Step up 3B → 8B; or template-only for common cases |
| End-to-end LLM latency under real desktop load | Smaller model; narrow what gets summarized |
| Exact Claude hook payload fields | Read transcript file directly by path |
| Capturing terminal output without tmux | Opt-in `pr <command>` wrapper (see [05-risks](05-risks-and-open-questions.md) Q2) |

None of these threaten the concept. The worst case is a less clever narrator, not
a broken one.

---

## The thing that is actually hard

It isn't any of the above. It's this:

> **A computer that talks to you is delightful for thirty minutes and
> unbearable by hour two.**

The existing "read every line of terminal output" mode already demonstrates the
failure mode. The engineering challenge is filtering and restraint — deciding
what is worth interrupting a human for. That's a taste problem, solved by
building it deliberately quiet and opening it up slowly, and it's why
[06-voice-and-tone.md](06-voice-and-tone.md) exists as a first-class document
rather than an afterthought.

**Recommendation: build it.** Phase 0 alone — the speech broker with the sticky
toggle — is a worthwhile deliverable that also fixes the overlapping-audio
fragility in the current setup.
