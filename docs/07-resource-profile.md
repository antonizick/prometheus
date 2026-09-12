# 07 — Resource Profile

**Requirement:** when Prometheus is toggled off, the machine must be exactly as
fast as if Prometheus had never been installed. When it's on but idle, the cost
must be negligible. The GPU in particular must not be held hostage.

This document is the contract. Phase 0 establishes the measurement harness so
these numbers are *verified*, not asserted.

> **Measured 2026-09-11, re-measured after Phase 1.** The tables below carry
> real numbers from `experiments/measure-overhead.sh`; see
> [experiments/overhead-results.md](../experiments/overhead-results.md). COLD
> is genuinely zero. WARM, with both voices *and* `prometheus-hypr` now
> resident, is **228 MB and effectively zero measurable CPU — 1 context
> switch across a 600-second idle window** (down from 357 in an interim run
> where this session's own animating title was actively driving real
> Hyprland events the whole time — see the note below), which is the number
> that actually proves the no-polling rule holds even with a second listener
> added.
>
> **Phase 1 also found a real shutdown bug via this re-measurement, not by
> inspection**: `prometheus-hypr`'s first cut didn't die on SIGTERM (a
> `selectors.select(timeout=None)` loop needs an active wakeup — a bare flag
> in the signal handler isn't enough, since PEP 475 makes Python silently
> retry an interrupted blocking syscall). Fixed with the standard self-pipe
> pattern; see [notes/2026-09-11-phase-1.md](../notes/2026-09-11-phase-1.md).
> Before the fix, COLD showed 1 process still `deactivating` well past the
> toggle.

---

## Three states, not two

The naive design — a daemon that runs always and checks a flag — is what causes
"background AI stuff" to quietly degrade a machine. Prometheus instead has three
resource states, and the toggle moves between them by **starting and stopping
processes**, not by setting flags.

### State COLD — toggled off

| Resource | Expected | **Measured** |
|---|---|---|
| Processes | **zero** | **0** ✓ |
| RAM | **0** | **0** ✓ |
| VRAM | **0** | **0** — no Ollama process on the GPU ✓ |
| CPU | **0** — no wakeups, no timers, no polling | **0** ✓ |
| Disk | ~5 GB of model weights sitting inert | unchanged |
| Battery | **no impact** | no resident process to draw any |

Everything is stopped: daemon, Hyprland listener, warm Piper, Ollama, and the
loaded model. `ollama stop <model>` releases the VRAM immediately rather than
waiting for a timeout.

The persisted "off" state is a file containing `0`. Files don't consume CPU.

The keybind still works because Hyprland bindings launch a command — they don't
require anything of ours to be resident. **The system is inert but not
uninstalled.** That's exactly the requirement.

> A useful way to check this claim: `pgrep -af prometheus` should return nothing
> at all, and `nvidia-smi` should show no Ollama process. If either shows
> something, the toggle is broken.

### State WARM — toggled on, nothing happening

| Resource | Expected cost | **Measured (Phase 0, single voice)** | **Measured (Phase 1, two voices + hypr)** |
|---|---|---|---|
| `prometheusd` | ~10–15 MB RAM, 0 % CPU (blocked on socket read) | **16.9 MB, 0.000 s CPU** | **17.2 MB, 0.000 s CPU** |
| Warm Piper (x1 or x2) | ~80–100 MB RAM each, 0 % CPU (blocked on stdin) | **100.0 MB, 0.000 s CPU** | **100.2 + 95.5 MB, 0.000 s CPU** |
| `prometheus-hypr` | ~5–15 MB RAM, 0 % CPU (blocked on socket read) | *(not built yet)* | **15.3 MB, 0.000 s CPU** |
| **VRAM** | **0 — no model loaded** | **0** ✓ | **0** ✓ |
| **Total** | — | **116.9 MB, 0.0000 % of one core** | **228.2 MB, 0.0000 % of one core** |

Over a 600-second idle window, every process in the Phase 1 measurement
accumulated **0.000 s of CPU and a single context switch total** — not
"almost none". Every thread is genuinely blocked on a socket read, an inotify
read, a pipe read, or a condition variable. (An earlier run during this same
session measured 357 context switches for `prometheus-hypr` alone over 10
minutes — not polling, but real Hyprland events: this very Claude Code
session's title was animating the whole time, and the listener correctly
woke up to receive and drop each one. Re-measured with the session genuinely
idle for a clean baseline.)

Every process is blocked on a read. They consume CPU only when an event actually
arrives, which is the correct behavior for event-driven code — no polling loops,
no timers, no periodic wakeups. On a 31 GB machine, ~100 MB is 0.3 % of RAM.

**The GPU is completely free in this state.** Games, video, CUDA work — all
untouched. This is the single most important line in the document, because
holding VRAM is the way a project like this would actually hurt the machine.

The warm Piper is the one arguable cost: ~100 MB held to save 0.3 s per
utterance. If that turns out to matter, it can drop to cold-start Piper per
utterance at the measured 0.3 s penalty — a config flag, decided by measurement.

### State HOT — a summary is being generated

| Resource | Cost | Duration |
|---|---|---|
| Ollama + model | 3–5 GB VRAM | Loaded on demand |
| GPU compute | Brief spike | ~1–2 s per summary |
| **Unload** | **Automatic after idle timeout** | `OLLAMA_KEEP_ALIVE` |

This is the only state with meaningful cost, and it exists only while actually
doing work. It ends by itself.

---

## The keep-alive tradeoff

The one genuine dial in the resource design. `OLLAMA_KEEP_ALIVE` controls how
long the model stays in VRAM after its last use:

| Setting | VRAM held | First-summary latency | Suits |
|---|---|---|---|
| `0` | Never | +2–4 s **every time** | Very occasional use |
| **`2m`–`5m`** | **During active work only** | +2–4 s after a lull | **Recommended default** |
| `30m` | Most of a work session | Rarely paid | Heavy continuous use |
| `-1` | **Always — rejected** | Never paid | Not worth 4 GB on an 8 GB card |

**Recommended: `5m`.** During a working session the second and subsequent
summaries are instant; after five idle minutes the GPU is handed back. You pay
the load cost once per burst of activity, not once per summary.

This is a one-line config change, so it can be tuned by feel after living with it.

Worth noting: on-demand loading makes the **pull-based briefing** design
(see [01-architecture.md](01-architecture.md)) fit even better. One briefing on a
keypress loads the model, answers, and lets it go — versus push narration
touching the model constantly throughout the day.

---

## Design rules that keep this true

These are constraints on implementation, not aspirations:

1. **No polling anywhere.** Every watcher blocks on a socket read or an inotify
   watch. If any component has a `sleep` in a loop, it's wrong.
2. **The toggle stops units; it does not set a flag.** `prometheus.target` with
   the components as `PartOf=` it, so one `systemctl --user stop` takes down the
   whole tree.
3. **Ollama is never enabled as an always-on service.** It is started with
   Prometheus and stopped with it, or socket-activated.
4. **Nothing is `WantedBy=default.target` except a tiny state-reader** that
   starts the tree only if the persisted state says on. Booting with Prometheus
   off must start nothing.
5. **No producer blocks.** Socket writes are fire-and-forget with a closed
   timeout. A hung daemon can never stall a shell prompt or a Claude turn.
6. **CPU-only inference is not used.** It would consume the cores the machine
   needs for actual work. GPU or nothing — and the RTX 2070 makes that easy.

---

## Measurement plan

Asserting low overhead isn't good enough. Phase 0 builds
`experiments/measure-overhead.sh` to record, for each state:

- `pgrep -af prometheus` — process count (must be 0 when cold)
- RSS of every Prometheus process
- `nvidia-smi --query-gpu=memory.used` — VRAM (must be unchanged when cold)
- CPU time accumulated over a 10-minute idle window (must be ~0 when warm)
- Wakeups per second — `powertop` or `/proc/<pid>/schedstat`, for battery impact

Results land in `experiments/overhead-results.md` and the numbers in the tables
above get replaced with measured ones. **If warm state costs more than the
budget (150 MB single-voice / 250 MB two-voice) or shows any measurable idle
CPU, the design is wrong and gets revised** — that's an acceptance criterion
in [04-build-plan.md](04-build-plan.md), not a nice-to-have.

**Phase 0 result: within contract**, with room to spare — 117 MB against a
150 MB budget, and no measurable CPU at all. **Phase 1 result: still within
contract** after adding `prometheus-hypr` — 228 MB against the 250 MB
two-voice budget, still no measurable idle CPU. Re-run the harness after any
phase that adds a resident process:

```bash
./experiments/measure-overhead.sh          # 10-minute idle window
./experiments/run-acceptance.sh            # every Phase 0 criterion
```

---

## What could still hurt the machine, honestly

| Risk | Mitigation |
|---|---|
| VRAM contention with a game or CUDA work | 5-minute keep-alive; model unloads when unused. Optional rule: skip summaries when another process holds significant VRAM. |
| Ollama pulling in heavy CUDA deps | One-time ~1–2 GB disk. No runtime cost when stopped. |
| Warm Piper's 100 MB | Configurable off, at 0.3 s/utterance |
| Whisper (voxtype) + summarizer both wanting GPU | `base.en` is ~150 MB — negligible. Real contention is unlikely; if it appears, the mic gate already stops speech during recording. |
| Journal file growing unbounded | Rotate; cap at a few MB |
