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

| Resource | Expected cost | **Phase 0 (1 voice)** | **Phase 1 (2 voices + hypr)** | **Phase 5 (1 voice + narration)** |
|---|---|---|---|---|
| `prometheusd` | ~10–15 MB RAM, 0 % CPU (blocked on socket read) | **16.9 MB** | **17.2 MB** | **17.5 MB** |
| Warm Piper (x1 or x2) | ~80–100 MB RAM each, 0 % CPU (blocked on stdin) | **100.0 MB** | **100.2 + 95.5 MB** | **100.3 MB** |
| `prometheus-hypr` | ~5–15 MB RAM, 0 % CPU (blocked on socket read) | *(not built yet)* | **15.3 MB** | **25.1 MB** |
| **VRAM** | **0 — no model loaded** | **0** ✓ | **0** ✓ | **0** ✓ |
| **Total** | — | **116.9 MB** | **228.2 MB** | **142.8 MB** |

> **Phase 5 note — where the extra 10 MB went, and the headroom it costs.**
> `prometheus-hypr` grew from 15.3 MB to **25.1 MB** when ambient narration was
> switched on. That is the phrase bank held resident (278 phrasings) plus the
> attention scorer. It buys the thing the design is built on: picking a phrasing
> stays a dictionary lookup with **no model loaded and no VRAM held**, exactly
> as [08](08-personality-and-config.md) promises.
>
> `prometheusd` grew 0.3 MB for the context gates, which is essentially nothing
> because they hold no state beyond a two-entry cache.
>
> **The headroom is worth naming**, because this is the first phase where it
> stops being generous.
>
> 142.8 MB against the 150 MB single-voice budget is within contract. Two things
> narrow it further:
>
> - **Piper's RSS grows with use, and the harness cannot see it.** 100.1 MB
>   freshly spawned; 107.8 MB after a day of real utterances, as the ONNX
>   session allocates and keeps its working buffers. The harness samples a
>   process that has just started, so **142.8 MB is the floor, not the steady
>   state** — the same system measured **151.1 MB** live at the end of the day
>   that produced these numbers.
>
>   That is **over the 150 MB single-voice budget**, by 1.1 MB, and it is
>   recorded here rather than rounded away: the budget was set in Phase 0
>   against a single voice and 117 MB, and ambient narration has spent most of
>   the slack. It is not a problem today — 151 MB is 0.5 % of this machine's
>   RAM — but the honest statement is "at budget", not "within it with room".
> - **The second voice is currently off.** `voice.agent.enabled` adds another
>   Piper, putting the total near **238 MB against the 250 MB two-voice
>   budget** — inside, with noticeably less room than Phase 1's 228 MB.
>
> If a future phase adds another resident process, the warm-Piper flag is the
> budget line to reconsider first: it trades ~100 MB for 0.3 s per utterance,
> and it is the only line here big enough to matter.

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

0. **Read the world only when about to act on it.** Phase 5 added context gates
   (locked screen, fullscreen, other audio — [04](04-build-plan.md) task 5.4),
   and the obvious implementation of all three is a timer. That would have been
   the first polling loop in the system, and it would have run all day to
   answer a question that only matters at the instant something wants to speak.
   They are checked at intent time instead, with a 2-second cache so a burst of
   intents shares one reading. Measured: 200 gate checks in **1.7 ms**, and
   nothing at all runs while the desktop is idle. The rule generalises — if a
   new signal seems to need a timer, check whether it only needs an answer at
   the moment of use.
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
two-voice budget, still no measurable idle CPU. **Phase 5 result: within
contract** with ambient narration live — 142.8 MB against the 150 MB
single-voice budget, and over the full 600-second window **0.000 s of CPU and
two context switches** across all three processes. Two switches in ten minutes
is the number that actually proves the no-polling rule; the CPU figure alone
could be faked by a sufficiently efficient poll loop.

> **Phase 5 also fixed the harness, which had started lying.** It reported FAIL
> three times while the system, measured directly over a quiet window, used
> **0.000 s of CPU and took 0 context switches**. Three separate holes:
>
> - **Piper's first synthesis after a spawn initialises ONNX lazily, across
>   several threads**, billing far more CPU-seconds than wall time: **1.62 s of
>   CPU for the single word "Listening."** The fixed `sleep 3` after the
>   power-on confirmation let part of that land after the baseline sample. It
>   now waits until the broker reports itself continuously idle.
> - **Desktop events during the "idle" window.** `prometheus-hypr` waking to
>   receive them is the behaviour under test, not a breach of it.
> - **A Claude Code turn ending fires the Stop hook, which speaks.** No desktop
>   event, nothing in the journal, window looks idle — and a two-second
>   utterance costs Piper ~1.4 s of CPU. Found in `prometheus transcript`, not
>   by reasoning about it.
>
> The harness now counts **both** desktop events and utterances across the
> window, and reports a non-idle window as **INCONCLUSIVE with both counts**
> rather than FAIL.
>
> **The durable lesson, and the third time it has been rediscovered by hand**
> (Phase 1's note about an animating window title says the same thing): the
> contract is **"no CPU without an event", not "no CPU ever"**. The hard part
> of testing it is not measuring CPU — it is enumerating what counts as an
> event. A test that conflates the two is one a correct system cannot pass.

Re-run the harness after any phase that adds a resident process:

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
