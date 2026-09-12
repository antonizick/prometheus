# 04 — Build Plan

Six phases. Each ends with something demonstrably working, and each has
acceptance criteria that can be checked rather than argued about.

**Sequencing principle:** build the plumbing before the intelligence, and the
*pull* path before the *push* path. The riskiest thing in this project is not a
technical failure — it's building a system that works perfectly and is
intolerable to live with. Getting a quiet, useful version into daily use early is
how that risk gets retired.

**Review gate:** before any narration is wired into the live desktop, the
candidate phrasings get **synthesized to audio and listened to**. Text that reads
fine on screen frequently sounds wrong. No component ships on the strength of
how its output looks in a terminal.

---

## Phase 0 — Foundation *(no AI at all)* ✅ **BUILT**

The speech broker, the toggle, and the resource contract. Nothing clever.

**Status (2026-09-11):** tasks 0.1–0.10 complete; 13/13 automatable acceptance
criteria pass via `experiments/run-acceptance.sh`, with both voices live. Nick
auditioned six candidates and chose **`en_GB-alba-medium`** for the `claude`
category. One criterion still needs a human: the reboot round-trip.
See [notes/2026-09-11-phase-0.md](../notes/2026-09-11-phase-0.md).

| # | Task |
|---|---|
| 0.1 | `prometheusd` — Unix socket, JSON intake, priority queue, dedup, rate limit, TTL |
| 0.2 | Warm Piper subprocess (`--json-input --output_raw`) → persistent `paplay`; respawn on death |
| 0.3 | State dir `~/.local/state/prometheus/` — `enabled`, `verbosity`; inotify watch |
| 0.4 | Mic gate — watch `$XDG_RUNTIME_DIR/voxtype/state`, hard-stop on `recording` |
| 0.5 | systemd user units + `prometheus.target`; **toggle stops units, doesn't set flags** |
| 0.6 | `prometheus say "..."` CLI — the test harness for everything after this |
| 0.7 | Keybinds in `bindings.lua` (toggle / shut-up / verbosity) after checking for collisions |
| 0.8 | `experiments/measure-overhead.sh` + record baseline numbers |
| 0.9 | `~/.config/prometheus/` — `config.json`, `persona.md`, `about-me.md`; hot-reload via inotify |
| 0.10 | Second Piper voice for the `claude` category — **audition candidates with Nick before picking** ✅ `en_GB-alba-medium` |
| 0.11 | `identity.name` + `prometheus name` — naming confirmed **by ear** before it commits; `spoken_as` respelling; optional two-step rename by dictation ✅ |

**Acceptance:** *(measured 2026-09-11)*

| Criterion | Target | Result |
|---|---|---|
| Speaks in the correct voice, `length_scale 0.7` intact | — | ⏳ confirm by ear |
| Time-to-first-sound | better than 310 ms | ✅ **48–93 ms** |
| Ten rapid `say` calls never overlap | 1 at a time | ✅ **max 1 concurrent**, 745 samples |
| Shut-up key stops speech mid-word | ~100 ms | ✅ **1–19 ms** |
| Toggle survives a full reboot, both directions | — | ⏳ needs a reboot |
| Speaking stops after voxtype enters `recording` | ~200 ms | ✅ **2–16 ms** |
| COLD: `pgrep -af prometheus` returns nothing | 0 | ✅ **0** |
| COLD: VRAM unchanged | 0 held | ✅ **no Ollama on GPU** |
| WARM: RAM | < 150 MB | ✅ **117 MB** |
| WARM: CPU over a 10-minute idle window | ~0 % | ✅ **0.000 s, 0 ctx switches** |
| Editing `config.json` takes effect without a restart | — | ✅ hot-reloaded via inotify |
| Naming: nothing commits until heard and confirmed | — | ✅ preview → confirm → write |
| Naming by voice needs two utterances, cancels on anything else | — | ✅ verified |
| Both voices distinguishable and pleasant | — | ✅ **alba** chosen by audition |
| WARM: RAM with the second voice | < 250 MB | ✅ **217 MB** |

> Phase 0 is independently worth having. It fixes the overlapping-audio
> fragility in the current `omarchy-tts-*` scripts even if we stop here.

---

## Phase 1 — Event journal + briefing *(the pull path)* ✅ **BUILT**

**Status (2026-09-11):** tasks 1.1–1.8 complete. `prometheus-hypr` runs as a
systemd user unit (`PartOf=prometheus.target`, so the toggle stops it with
everything else) and journals a filtered Hyprland event stream; `prometheus
brief` and `experiments/replay-scoring.py` read it. See
[notes/2026-09-11-phase-1.md](../notes/2026-09-11-phase-1.md).

| # | Task |
|---|---|
| 1.1 | Hyprland event listener → parse `.socket2.sock` ✅ |
| 1.2 | Append-only journal at `~/.local/state/prometheus/journal` (JSONL, rotated) ✅ |
| 1.3 | App-class → friendly-name map (`brave-browser` → "Brave") ✅ `config.json` → `hypr.app_names` |
| 1.4 | Event filter: allowlist, debounce, **drop `windowtitle` churn** ✅ |
| 1.5 | `prometheus brief` — template-only first version, no LLM ✅ |
| 1.6 | `SUPER + ALT + B` binding ✅ (moved from `SHIFT` — see Phase 0's key collisions) |
| 1.7 | **Interest scoring** — novelty, rarity, odd-hour, recency; tunable weights ✅ `experiments/replay-scoring.py` |
| 1.8 | Replay harness: run scoring over journalled history to see what *would* have been spoken ✅ |

**Acceptance:**

| Criterion | Result |
|---|---|
| Journal captures window/workspace events with no measurable CPU cost | ✅ **228 MB total warm RSS (two voices + hypr listener), 1 context switch over a 600s idle window** — re-measured in [07](07-resource-profile.md). Caught a real bug doing this: the listener's first cut didn't die on `SIGTERM` (a `selectors.select(timeout=None)` loop needs an active wakeup, not just a flag in the handler — fixed with a self-pipe) |
| **The spinner-title case produces zero journal spam** | ✅ **and a second, undocumented instance of the same bug found live**: this Claude Code session's animating title also re-fires `activewindowv2` on every frame, not just `windowtitlev2` — confirmed against the live socket while building this. Fixed by keying the debounce off whether the focused *address* changed, not off event arrival |
| `brief` gives a sensible spoken account of the last few minutes | ✅ template-only; see worked example below |
| Alt-tabbing through six windows produces one event, not six | ✅ verified with a direct unit test driving `Listener._on_activewindow`/`settle_focus` (six synthetic focus changes + five duplicate re-announcements of the settled window → exactly one journal entry, `coalesced: 6`) |

```
$ prometheus brief --print
In the last 15 minutes: opened the terminal and Brave; spent time in the
terminal and Brave; switched workspace 2 times.
```

> Deliberately no narration yet. `prometheus-hypr` only journals; nothing it
> sees is spoken. Interest scoring (1.7) runs offline, in the replay harness,
> against the journal — not live — so narration in a later phase can be tuned
> against real data instead of guesses.

---

## Phase 2 — Local LLM ✅ **BUILT**

**Status (2026-09-11):** tasks 2.1-2.10 complete. Nick played the staged
review and approved the bank as-is — nothing cut, register unchanged. See
[notes/2026-09-11-phase-2.md](../notes/2026-09-11-phase-2.md) for 2.1-2.6 and
[notes/2026-09-11-phase-2b.md](../notes/2026-09-11-phase-2b.md) for 2.7-2.10.
Task 2.4 resolved by ear: **`qwen3:4b-instruct` confirmed as the runtime
model** (already the config default). `qwen3:1.7b` is the documented fallback
if resource pressure ever forces a downgrade — not `llama3.2:3b`, which
benchmarking disqualified (see [03](03-model-selection.md) and model-bench.md
finding 2).

The authoring model changed on evidence: **`gemma2:9b`, not `qwen3:8b`** —
head-to-head on the real authoring prompt, 43 % of its candidates survived
validation against qwen3:8b's 18 %, and it writes plain speech where qwen3:8b
writes invented detail. Two findings from that comparison are in
[03](03-model-selection.md); the bigger one — that forty phrasings per event
was the wrong target in the first place — is in
[08](08-personality-and-config.md).

| # | Task |
|---|---|
| 2.1 | `pacman -S ollama-cuda`; confirm GPU inference; **do not enable always-on** ✅ |
| 2.2 | Assemble ~20 real samples from this machine (builds, tests, errors, Claude messages) ✅ `experiments/samples.jsonl` |
| 2.3 | Benchmark candidates from [03](03-model-selection.md) on latency, VRAM, length discipline, speakability ✅ `experiments/model-bench.md` |
| 2.4 | **Blind listening test** — Nick ranks summaries *as audio* ✅ `qwen3:4b-instruct` wins; `qwen3:1.7b` acceptable under resource pressure |
| 2.5 | `prometheus-llm` wrapper: prompt, `num_predict` cap, 4 s timeout, post-filter, fail-silent ✅ `bin/prometheus-llm` |
| 2.6 | On-demand load + `OLLAMA_KEEP_ALIVE=5m`; verify VRAM is released ✅ `experiments/keepalive-results.md` |
| 2.7 | Upgrade `brief` to LLM synthesis ✅ `prometheus-llm brief`, with the template as fallback — a pulled briefing never answers silence |
| 2.8 | **`prometheus regenerate`** — offline phrase-bank authoring from `persona.md` + `about-me.md` ✅ `bin/prometheus-phrasebank`, `config/phrasebank-spec.json` |
| 2.9 | Bank selection at runtime: weighted pick, `avoid_last_n`, auto-regen on persona/register change ✅ `prometheus phrase` |
| 2.10 | **Listening review of a generated bank with Nick** before it goes live ✅ **heard and approved as-is** — no phrasings cut, no register change |

**Acceptance:** *(2.1-2.6, measured 2026-09-11)*

| Criterion | Target | Result |
|---|---|---|
| Summary latency p95, model warm | < ~2.5 s | ✅ **0.38-1.25s** across 5 candidates, worst case (qwen3:8b) still 2x under budget |
| Outputs under 30 words | > 90% | ✅ **90-100%** across candidates |
| No paths, code, markdown, bullets survive the post-filter | — | ✅ `bin/prometheus-llm`'s `post_filter()` strips regardless of model behavior — verified against a model that leaked a real path (`~/Documents/...`) in benchmarking |
| Pass/fail outcomes never reported backwards | — | ✅ **true for both models actually in use** — `qwen3:4b-instruct` (confirmed by ear as the runtime model, 0/20 hallucinations) and `qwen3:1.7b` (the resource-pressure fallback, mild-only hallucinations, never a wrong outcome). `llama3.2:3b` remains disqualified — see model-bench.md finding 2 — and is no longer the documented fallback (03-model-selection.md updated) |
| VRAM returns to baseline within ~6 minutes of last use | — | ✅ **141s**, automatic, `keep_alive` left at `5m` (never `-1`) |
| Ollama unreachable → system degrades to silence, never hangs | — | ✅ verified live: `bin/prometheus-llm` timed out silently on a misconfigured model tag before the fix was found, never crashed or printed garbage |
| Ollama never enabled as an always-on service | — | ✅ pacman's `ollama.service` stays `disabled`; the Prometheus-scoped `prometheus-ollama.service` has no `[Install]` section and is started only on demand |
| **Phrase bank: 40 usable variants per event, no duplicates, all within the word cap, all recognisably the same register** | — | ⚠️ **target revised, and the revision is the finding.** No duplicates, all within the word cap, all one register — ✅, enforced mechanically by the validator and re-checkable with `prometheus-phrasebank verify`. But **40 per event was wrong**: most moments do not contain forty true things to say, and a model asked for forty invents the remainder. Targets are now per-moment in `phrasebank-spec.json` (24 for a failed command, 12 for a workspace switch, 10 for the toggle confirmations). Reasoning in [08](08-personality-and-config.md) |
| **Runtime bank lookup adds no measurable latency and loads no model** | — | ✅ **p50 9-20 µs, p95 12-28 µs** in-process across runs, bank load under 1 ms once. No model, and a test asserts the picker opens no socket. `experiments/test-phrasebank.py` |
| `avoid_last_n` holds — nothing repeats inside the window | — | ✅ verified over 400 consecutive picks at bank sizes 30, 16 and 10; degrades gracefully to least-recently-used when the bank is smaller than the window (which the 10-variant toggle banks are) |
| The bank sounds like one system, and is worth hearing twice | — | ✅ **approved by ear** — Nick played `session/00-whole-session.wav` and the by-event sequences, and cut nothing |
| Changing `register` to `terse` and regenerating audibly changes the voice | — | ⏳ mechanism built and wired to the fingerprint — `register` is part of what marks a bank stale, and seeds are withheld from the bank under a non-neutral register so the change is not diluted. **Not yet confirmed by ear**, which is the only confirmation that counts |
| **Nothing the model writes is banked unchecked** | — | ✅ validator rejects ~50 %; every rejection logged with its reason. Caught real instances of: a failed build described as "still waiting", a successful one as "timed out", an instruction ("Check the build log"), invented screen detail ("scrolling through Brave's tabs"), and nine of sixteen `claude_blocked` lines that never said *Claude* |
| Briefings answer, even when the model doesn't | — | ✅ `prometheus brief` falls back to its own deterministic template on any LLM failure. A pulled briefing never answers silence |

---

## Phase 3 — Claude Code integration *(highest value)* ✅ **BUILT**

**Status (2026-09-11):** tasks 3.1-3.7 complete. See
[notes/2026-09-11-phase-3.md](../notes/2026-09-11-phase-3.md) and
[experiments/hook-schema-findings.md](../experiments/hook-schema-findings.md)
(task 3.1's verification, including where a cold LLM guess at the payload
schema turned out half-fabricated). One deliberate deviation from 3.3's
literal wording: the real `Stop` payload carries `last_assistant_message`
directly, confirmed by live capture, so the handler reads that rather than
opening the transcript file — simpler, and avoids the transcript's documented
async-write lag entirely. `bin/prometheus-claude` is the single binary for
both hooks; wired into `~/.claude/settings.json` (`"async": true`, `"timeout":
20`) by `install.sh`, which now also manages that file idempotently.

| # | Task |
|---|---|
| 3.1 | **Verify actual hook payload schema** — log raw stdin from each hook first ✅ |
| 3.2 | `Notification` hook → `critical` priority ("Claude is waiting for you") ✅ |
| 3.3 | `Stop` hook → read transcript, extract final assistant message ✅ (via `last_assistant_message`, not the transcript file — see above) |
| 3.4 | Short-circuit: messages < 25 words spoken directly, no LLM ✅ `speak.claude_finished.short_circuit_words` |
| 3.5 | Longer messages → summarizer ✅ |
| 3.6 | Strip code blocks, paths, markdown before speech ✅ |
| 3.7 | Multi-session disambiguation — which project is talking? ✅ best-effort `/proc` scan, see notes |

**Acceptance:**
- Walking away from a blocked agent session gets you told about it
- Session summaries are accurate about what changed
- **Zero added API tokens** — confirmed by inspecting usage
- Hook failures never block or slow a Claude turn
- Two concurrent sessions don't produce confusing crosstalk

> Task 3.1 is a genuine dependency, not ceremony. Everything here rests on the
> hook payload shape, so it gets verified empirically before anything is built on it.

---

## Phase 4 — Shell integration ✅ **BUILT**

**Status (2026-09-11):** tasks 4.1-4.5 complete. See
[notes/2026-09-11-phase-4.md](../notes/2026-09-11-phase-4.md). Decision logic and
CLI wiring verified with `say`/`phrase`/`summarize` mocked out, plus one
real-binary integration check on inputs guaranteed silent by config (no risk
of audio); **not yet confirmed by ear** — the phrase-bank wording itself was
already approved in Phase 2, but a live failed/long-running command hasn't
actually been heard yet, and Nick asked to be warned before anything audible
runs.

| # | Task |
|---|---|
| 4.1 | `PROMPT_COMMAND` hook: capture command, exit code, duration ✅ `shell/prometheus.bash` — DEBUG trap + `$EPOCHREALTIME`, no external processes on the command path |
| 4.2 | Exit-code narration — **only** long-running or failed commands ✅ `bin/prometheus-shell exit-code`, gated by `speak.command_failed` / `speak.command_succeeded` (`enabled`, `min_duration_secs`) |
| 4.3 | `pr <command>` opt-in wrapper with output capture ✅ tees to `$XDG_RUNTIME_DIR/prometheus/`, preserves the real exit code via `PIPESTATUS[0]` |
| 4.4 | Route captured output through the summarizer ✅ `bin/prometheus-shell pr` → `prometheus-llm summarize -c shell`, tailed to 200 lines / 6000 chars first |
| 4.5 | Resolve the tmux question (see [05](05-risks-and-open-questions.md) Q2) ✅ **A + B**, as recommended — exit-code narration is free and always on, `pr` is the opt-in rich path; tmux (C) and full session logging (D) stay out of scope |

**Acceptance:**
- Fast successful commands produce **silence** ✅ `command_succeeded.enabled: false` by default — every fast-success and (until raised) slow-success case is silent; verified for both in isolation
- A 40-second failure is announced accurately — ⏳ decision logic verified (mocked), not yet heard live
- `pr make test` gives a useful spoken summary — ⏳ decision logic verified (mocked), not yet heard live
- **Prompt latency increase is unmeasurable** ✅ measured: ~10 µs/command baseline vs ~156 µs/command with the hook sourced and Prometheus off (fast-path file read, no fork), ~166 µs/command with Prometheus on (backgrounded fork). All three are 3+ orders of magnitude below anything a person can perceive. `disown`ing the background dispatch also had to be paired with `{ … } 2>/dev/null` — bash's own job-control "[1] PID" notice isn't silenced by redirecting the child's output or by a bare `disown`, and would otherwise have printed after every narrated command

---

## Phase 5 — Living with it

The phase that decides whether this gets used or turned off.

| # | Task | |
|---|---|---|
| 5.1 | Tune from real journal data — what was spoken that shouldn't have been? | ✅ |
| 5.1a | **Revisit `speak.claude_finished.min_turn_secs`** — deferred from Phase 3 on purpose. Currently `0`, so it speaks after every Claude turn; almost certainly too chatty, but the right number is found by ear, not by guessing. Evidence: `prometheus feedback --list`, `prometheus transcript -v` | ✅ |
| 5.2 | Verbosity profiles: quiet / normal / chatty | ✅ |
| 5.3 | Voice and tone pass (see [06](06-voice-and-tone.md)) — listened to, not read | ◑ staged |
| 5.4 | Context gates: screen locked, fullscreen, other audio playing | ✅ |
| 5.5 | Migrate `omarchy-tts-read-cursor` / `-terminal-live` to route via the broker | ✅ |
| 5.6 | Re-measure overhead; update [07](07-resource-profile.md) with real numbers | ✅ |
| 5.7 | Write the operator's manual ([11-living-with-it.md](11-living-with-it.md)) | ✅ |

**Built 2026-09-12** — see [notes/2026-09-12-phase-5.md](../notes/2026-09-12-phase-5.md).

Headline, replayed against 7.8 hours of real journal: ambient narration as
designed would have spoken **14.7 times an hour** with **46 %** of those
utterances carrying any reason beyond a coin flip. After tuning: **1.2 times an
hour, 100 % carrying a reason**, and the 15 % target rate is actually hit
(it was achieving 9.6 %).

Three of the five interest signals turned out to be dead against real data —
`returned` had literally never fired, because its 3600-second threshold sat
past the longest real gap of 3454 seconds. Workspace switches, which docs/01
made the always-on `quiet` floor, turned out to be the *most* frequent event
class (90 in 7.8 h, median gap 1.4 s) and were absorbing ~90 % of all ambient
speech.

5.3 is **staged, not signed off**: the phrase bank was audited across four
regenerations and **53 lines cut** — `"Files changed, Claude Code."` for a
window gaining focus, `"Claude Code's running on Prometheus."` for a *blocked*
agent, `"Claudes awaits your response."` — and every gap that admitted them is
closed at the source, in `banned_words`, `unknowable_words` and seven new
validator rules. The bank is back at target (284 phrasings) and clean.

But the listening pass itself is Nick's, by ear, and that is the whole point of
the task: three of those defects were only findable in `prometheus transcript`,
downstream of the speaker, after passing every static check.
`experiments/phrasebook/play.sh` ⚠ makes sound.

**Acceptance:**
- A full working day with it on, without wanting to turn it off — *the only
  acceptance criterion that really matters* → **outstanding.** Narration went
  live at the end of this phase; the day it has to survive hasn't happened yet.
- Only one thing ever holds the audio device → **met.** The three
  `omarchy-tts-*` paths were the last producers spawning their own Piper, and
  they now submit intents (task 5.5). They also inherit the microphone gate and
  the shut-up key by doing so.
- Documented numbers match measured ones → **met**, and the harness that
  checks it was wrong three different ways before it agreed: 0.000 s CPU and
  two context switches across a 600-second window, 142.8 MB against a 150 MB
  budget.

---

## Phase 6 — Optional, only if earned

Not committed to. Listed so they're not lost, and explicitly deferred.

- Full two-way conversation (voxtype → LLM → spoken answer): "what's my disk usage?"
- Notification interception (`dunst`/`mako`) → spoken alerts
- Per-app narration rules
- Wake-word hands-free operation
- A different voice per category (agent vs. system) — cheap, possibly clarifying
- Voxtype's unused `[output.post_process]` hook for LLM dictation cleanup

---

## Rough effort

| Phase | Effort | Value delivered |
|---|---|---|
| 0 | 1 session | Reliable speech infrastructure; fixes existing overlap bugs |
| 1 | 1 session | Briefing on demand; real data on what happens |
| 2 | 1–2 sessions | Local summarization at zero cost |
| 3 | 1 session | **The biggest single win** |
| 4 | 1 session | Terminal awareness |
| 5 | Ongoing | Whether it's actually livable |

**If time is short, Phases 0 + 3 alone deliver most of the value**: a reliable
voice, and never again losing ten minutes to an agent that stopped to ask a
question while you looked away.
