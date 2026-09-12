# 05 — Risks and Open Questions

## The risk that actually matters

**R1 — It becomes annoying and gets turned off forever.** *(High likelihood,
fatal impact)*

Every other risk here is an engineering problem with a known fix. This one isn't.
A talking computer is charming for half an hour and exhausting by hour two, and
the existing "read every line of terminal output" mode already demonstrates the
shape of the failure.

It's why the architecture is built the way it is:

- Default posture is **silence**; things earn their way into being spoken
- **Pull before push** — briefing on a keypress rather than constant narration
- Allowlists, not denylists — unknown events say nothing
- Ambient speech is *droppable* by design
- Phase 1 journals events for days before anything narrates them, so tuning is
  driven by what actually happens on this desktop rather than guesses
- An instant, unconditional shut-up key

The mitigation is restraint, and restraint has to be structural. If it depends on
us remembering to be tasteful, it will fail.

---

## Technical risks

**R2 — Speech backs up behind itself.** At `length_scale 0.7` Piper speaks about
**4 words per second**. Twelve queued events is a minute of monologue about
things that already happened. *Mitigated:* TTL expiry, ambient dropping, rate
limits, hard word caps. The queue must never grow faster than it drains.

**R3 — Audio feedback loop.** Piper's output gets picked up by the mic and
transcribed as dictation. *Mitigated:* the voxtype state file gate — stop
speaking within ~200 ms of `recording`. Verified present and readable. Push-to-talk
makes this much easier than always-on listening would. Residual risk if speakers
are loud and the mic is sensitive; headphones eliminate it entirely.

**R4 — Event spam from title churn.** **Already observed, not hypothetical** —
the feasibility capture showed this session's own window title animating a
spinner (`◐`/`◑`) several times a second. *Mitigated:* ignore `windowtitle`
events by default; debounce; dedup keys.

**R5 — Small-model summaries are too long or unspeakable.** The characteristic
failure is verbosity and markdown, not stupidity. *Mitigated:* `num_predict` cap,
explicit prompt constraints, mechanical post-filtering, the `NOTHING` escape
hatch. *Fallback:* step up to 8B, or template more cases.

**R6 — Latency makes it feel laggy rather than conversational.** *Mitigated:*
warm Piper, no LLM on the ambient path, 4 s timeout with fail-silent.
*Fallback:* smaller model; narrow what gets summarized.

**R7 — VRAM contention.** A 3–5 GB model on an 8 GB card competes with games and
CUDA work. *Mitigated:* on-demand loading, 5-minute keep-alive, full unload when
toggled off. *Optional:* skip summaries when another process holds significant
VRAM. See [07-resource-profile.md](07-resource-profile.md).

**R8 — Claude hook payloads differ from assumption.** *Mitigated:* Phase 3 Task
3.1 logs the raw payloads before anything is built on them. *Fallback:* read the
transcript file directly by path.

**R9 — A hook slows down Claude Code or the shell.** Unacceptable — this system
must be invisible when it isn't speaking. *Mitigated:* hooks fire-and-forget to a
socket and return immediately; summarization happens in the daemon, never inline.

**R10 — Omarchy updates break integration points.** Config is Lua and evolving.
*Mitigated:* keep changes minimal and in user config files; document every
touched file; [02](02-system-inventory.md) is re-verifiable.

**R11 — Two Claude sessions talking at once.** Crosstalk between projects.
*Mitigated:* include a project identifier; consider narrating only the focused
session's results.

---

## Open questions — need Nick's input

These change what gets built. The rest can be decided as we go.

### Q1 — What is worth interrupting you for? *(Most important)*
The single highest-value input. Some candidates:

| Event | Worth speaking? |
|---|---|
| Claude finished responding | ? |
| **Claude is blocked waiting on you** | *(assumed yes — the strongest case)* |
| A long command failed | ? |
| A long command succeeded | ? |
| App opened / closed | ? |
| Workspace switched | ? |
| Browser navigation | ? |

My instinct: **only** "Claude is waiting" and "a long command failed" deserve
unprompted speech. Everything else belongs in the briefing. But this is a
preference question, not a technical one.

### Q2 — Terminal output capture: how much do you want?
Reliable capture in a plain terminal is the one genuinely awkward part.
**Note: tmux isn't currently running**, so the existing live-read feature does
nothing today. Options:

| Option | Coverage | Cost |
|---|---|---|
| **A. Exit codes only** | Every command | Free, zero setup, no output text |
| **B. `pr <cmd>` opt-in wrapper** | Only what you mark | Requires typing `pr` |
| **C. Always run inside tmux** | Everything | Changes your terminal habits |
| **D. Full session logging** | Everything | Heavier; privacy considerations |

Recommendation: **A + B.** A is free and covers failures; B gives rich summaries
where you actually want them, without changing how you work.

### Q3 — Personality? ✅ **RESOLVED 2026-09-11 — neutral**
Same information, three registers:

- **Terse:** "Build failed. Two errors."
- **Neutral:** "The build failed with two errors in the parser."
- **Warm:** "Build's unhappy — a couple of errors in the parser."

Terse wears best over months; warm is nicer for ten minutes. Recommendation:
**neutral, trending terse.** Worth hearing samples before deciding — this is
exactly the kind of thing that reads fine and sounds wrong.

**Decided by ear, not on the page.** Nick played the full phrase-bank review
(`experiments/phrasebook/`) at neutral and approved it as-is, cutting nothing.
It stays `"register": "neutral"`. Changing it is one word plus
`prometheus regenerate`, so this is reversible at any point — see
[10-feedback-and-tuning.md](10-feedback-and-tuning.md).

### Q4 — Should it ever address you by name, or ask questions back?
Purely a taste call. Two-way conversation is Phase 6 and easy to bolt on later if
wanted, so nothing is foreclosed by saying no now.

### Q5 — Keybinding collisions? ✅ **RESOLVED — the whole family moved to SUPER+ALT**
Proposed: `SUPER+SHIFT+S` (toggle), `SUPER+SHIFT+X` (shut up),
`SUPER+SHIFT+B` (brief), `SUPER+SHIFT+ALT+S` (verbosity).
`SUPER+SHIFT+S` looks like a likely screenshot collision. Needs checking against
`omarchy menu keybindings --print` — and any preference you have on which keys.

**Checked, and worse than feared**: all three `SUPER+SHIFT` proposals collide
with Omarchy webapp defaults (Google Maps, X, Browser). The family moved to
`SUPER+ALT`, which Omarchy barely uses. The same trap caught the feedback key
later — `SUPER+ALT+F` is Omarchy's "Full width", so it went to `+N` for "note".

| Keys | Action |
|---|---|
| `SUPER + ALT + P` | Toggle the voice on/off |
| `SUPER + ALT + X` | Shut up |
| `SUPER + ALT + V` | Cycle verbosity |
| `SUPER + ALT + B` | Brief me |
| `SUPER + ALT + N` | Note feedback |

**Moral, now twice-confirmed:** check `hyprctl binds -j` for the *live* binding
set, not just the config files. Both collisions were invisible in the files.

### Q6 — Confirm the voice stays fixed? ✅ **RESOLVED — yes, plus a second voice**
Assumed yes: `en_GB-alan-medium` at `length_scale 0.7`, unchanged.

One question within that: **would a second, distinct voice for agent output vs.
system chatter be useful, or annoying?** It's nearly free to implement (another
Piper voice file) and would make "this is Claude talking" versus "this is your
desktop talking" instantly distinguishable without a spoken prefix. Default
assumption: no — one voice, unchanged.

**The default assumption was wrong.** Nick auditioned six candidates and chose
**`en_GB-alba-medium`** for the `claude` category; the machine still speaks as
Alan. Being able to tell the agent from the desktop without parsing the words
turned out to be worth having. `prometheus voice single` reverts to one voice
in one command, and costs nothing when off — the second Piper process is not
spawned at all.

---

## Explicit non-goals

Worth naming so scope stays honest.

- **Not a screen reader.** Doesn't replace Orca or the existing read-from-cursor
  script — those read text verbatim on demand, which is a different job.
- **Not accessibility-grade.** Best-effort ambient narration; anyone depending on
  it for access should use a real screen reader.
- **Not always-listening.** Voxtype stays push-to-talk.
- **Not cloud.** No paid API calls, ever, by design.
- **Not a replacement** for the existing `omarchy-tts-*` scripts — they stay, and
  eventually route their audio through the same broker.
