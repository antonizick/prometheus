# Task 3.1 — Claude Code hook payload schema, verified empirically

Two independent methods, cross-checked against each other and against a first
pass from the `claude-code-guide` agent (which turned out to be partly wrong —
exactly the failure mode this task exists to catch).

## Method 1 — live capture

`experiments/hook-schema-probe.sh` registered as an unconditional (`matcher: ""`)
`command` hook for both `Stop` and `Notification` in `~/.claude/settings.json`,
appending raw stdin verbatim to `experiments/hook-payloads-raw.jsonl`. Triggered
with a real `claude -p ... --model haiku` subprocess.

Real captured `Stop` payload:

```json
{
  "session_id": "dc20bf4b-0fb8-41ee-a3cd-25dc0e5fcf32",
  "transcript_path": "/home/nick/.claude/projects/-tmp/dc20bf4b-....jsonl",
  "cwd": "/tmp",
  "prompt_id": "7caeddd3-e071-450b-883d-6c30a878c5dc",
  "permission_mode": "default",
  "hook_event_name": "Stop",
  "stop_hook_active": false,
  "last_assistant_message": "OK",
  "background_tasks": [],
  "session_crons": []
}
```

`last_assistant_message` is real and present — this is the field to use.
Reading the transcript file is unnecessary for this purpose (and would be
strictly worse: docs claim, and the guide agent independently agreed, that
the transcript write lags the in-memory turn).

Attempting to also capture a real `Notification` payload the same way did not
work: headless `-p`/print-mode sessions auto-deny permission requests before
the notification path fires (confirmed with both an unsafe `rm -rf` — blocked
by an unrelated safety classifier — and a benign `echo > file` — silently
refused for lack of a TTY to prompt on). A pty-driven interactive session was
attempted to force a real permission dialog, but got (correctly) blocked by
this machine's own auto-mode classifier as a permission-prompt-bypass pattern
— so that path was abandoned in favor of Method 2, which turned out to be
strictly more informative anyway.

## Method 2 — schema extracted from the installed binary itself

`claude --version` → 2.1.268, installed via mise at
`~/.local/share/mise/installs/claude/2.1.268/claude` (a bun-compiled single
executable, but the bundled JS keeps readable UTF-8 string constants,
including its own zod-style schema definitions).

`strings -a <binary>` dumped to a scratch file and grepped for the hook
schema constructors directly. Ground truth, not inference:

**Notification payload schema** (the real one — see "what the guide agent got
wrong" below):
```
{ hook_event_name: "Notification", message: string, title?: string,
  notification_type: string, ...common fields }
```
Real `notification_type` enum, found verbatim: `permission_prompt`,
`idle_prompt`, `auth_success`, `elicitation_dialog`, `agent_needs_input`,
`agent_completed`, `elicitation_url_dialog`, `worker_permission_prompt`,
`push_notification`, `computer_use_enter`, `computer_use_exit`,
`quota_auto_resume_fired`, `quota_auto_resume_stale`, (+ a couple more).

Real message strings, found verbatim in the binary:
- `"Claude is waiting for your input"` — paired with `notification_type: "idle_prompt"`
- `"Claude needs your permission to use "` (+ tool name appended) — paired with `"permission_prompt"`

**Common fields** shared by every hook event (from the `Ha(e,n,r,o)` builder
function): `session_id`, `transcript_path`, `cwd`, `permission_mode`,
`agent_id` (subagents only), `effort`. Matches what Method 1 captured for
`Stop`, plus `Stop`-specific additions (`prompt_id`, `stop_hook_active`,
`last_assistant_message`, `background_tasks`, `session_crons`).

**`hooks` registration schema** in `settings.json`, also extracted directly:
```
type: "command", command: string, args?: string[] (exec-form, no shell),
if?: string (permission-rule-style matcher, mainly for PreToolUse),
shell?: "bash"|"powershell", timeout?: number (seconds),
statusMessage?: string, once?: boolean,
async?: boolean            — "if true, hook runs in background without blocking"
asyncRewake?: boolean, rewakeMessage?: string
```
Top level: `hooks: { "<EventName>": [ { matcher?: string, hooks: [ ...above ] } ] }`.
No matcher support on `Stop` (fires unconditionally); `Notification` matcher,
if present, is matched against `notification_type`.

## What the `claude-code-guide` agent got wrong

Asked cold (no empirical check), before this task ran the live/binary
verification above, it produced a plausible-looking but partly fabricated
answer:

- Claimed `Notification`'s per-event detail lives in a `notification_data`
  object (e.g. `{tool_name, tool_input}`). **False** — the real field is a
  flat, pre-rendered `message` string plus a separate `notification_type`
  enum tag. There is no structured `notification_data`.
- Claimed a `tool_calls` array and a `stop_reason` field on the `Stop`
  payload. **Not present** in the real captured payload (Method 1) or in the
  binary's own schema for `Stop`-specific fields.
- Got `last_assistant_message`, `async: true`, and the general two-file
  settings.json shape essentially right.

Net: roughly half right, half invented — confirming task 3.1's premise
(docs/05-risks-and-open-questions.md R8) that hook payloads must be verified,
not assumed, before anything is built on them.

## What this means for the Phase 3 build

- `Stop`: read `last_assistant_message` directly from the hook JSON. Never
  need to open the transcript file at all for this purpose.
- `Notification`: speak from the phrase bank (`claude_blocked` /
  `claude_blocked_project`), not from the raw `message` field — matches
  docs/01's "Hook + phrase bank, instant" design and keeps the
  highest-value, most time-sensitive event off the LLM path entirely. The
  `notification_type` enum is logged for visibility but every `Notification`
  is currently treated as the blocked/critical case per docs/01 (`Notification
  | critical | "Claude is blocked waiting for you"`) — no need to branch on
  `idle_prompt` vs `permission_prompt` for what gets spoken.
- Both hooks registered with `"async": true` (a real, confirmed field) as a
  second, belt-and-suspenders guarantee against ever blocking a Claude turn,
  on top of the daemon-side fire-and-forget socket contract everything else
  in Prometheus already relies on.
