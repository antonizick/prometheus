# shell/prometheus.bash — Prometheus shell integration (Phase 4).
#
# Sourced from ~/.bashrc by install.sh. Two independent pieces:
#
#   Mode A (always on, docs/01 "prometheus-shell")
#     A DEBUG trap + PROMPT_COMMAND pair capture every top-level command,
#     its exit status, and its wall-clock duration, and hand the *decision*
#     of whether to say anything to `prometheus-shell exit-code` — this file
#     never decides that itself, only whether to ask.
#
#   Mode B, opt-in (docs/01 "Mode B — summarized output")
#     The `pr` function: `pr <command>` tees output to a temp file and
#     routes it through `prometheus-shell pr` for an LLM summary.
#
# Two hard constraints from docs/04 Phase 4 shaped everything below:
#
#   "Fast successful commands must produce silence." — a config decision
#   (config.json speak.command_succeeded.enabled is false out of the box),
#   enforced in bin/prometheus-shell, not here.
#
#   "Shell prompt latency must not increase measurably." — this file does
#   only bash-builtin work (arithmetic on $EPOCHREALTIME, string tests, one
#   file read) on the command path. The one subprocess it ever starts
#   (prometheus-shell) is launched with `&` + `disown`, so the prompt never
#   waits on it — and per ADR-0002 ("off" means zero processes, not a muted
#   flag), that fork doesn't happen at all when Prometheus is toggled off:
#   __prometheus_enabled reads the persisted state file directly (a `read`
#   builtin, no subprocess) before anything else runs.

[[ -n $BASH_VERSION ]] || return    # bash-only: DEBUG trap + EPOCHREALTIME
[[ $- == *i* ]] || return            # interactive shells only

__PROMETHEUS_BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../bin" && pwd)"
__PROMETHEUS_STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/prometheus"
__PROMETHEUS_ENABLED_FILE="$__PROMETHEUS_STATE_DIR/enabled"
__PROMETHEUS_RUN_DIR="${XDG_RUNTIME_DIR:-/tmp}/prometheus"

__prometheus_enabled() {
    local v=""
    [[ -r $__PROMETHEUS_ENABLED_FILE ]] && v=$(<"$__PROMETHEUS_ENABLED_FILE")
    [[ $v == "1" ]]
}

# --------------------------------------------------------------------------
# Mode A — capture + exit-code narration
#
# The DEBUG trap fires before every simple command bash runs at top level,
# but NOT for commands inside a function body (bash doesn't propagate DEBUG
# into functions unless `set -o functrace` is on, which nothing here sets) —
# verified empirically before relying on it. That means the only trap firing
# our own precmd function ever causes is for its own top-level invocation
# from PROMPT_COMMAND; everything precmd does internally is invisible to it.
#
# __prometheus_shell_armed is the guard: preexec only captures when armed,
# then disarms itself, so a pipeline's later stages or a compound command's
# later clauses (each their own top-level firing) don't overwrite the first
# capture. precmd re-arms at the very end, right before the next real prompt.
#
# Known limitation, inherent to $BASH_COMMAND rather than fixable here: for
# a pipeline (`make test | tee log`), it only ever holds the first stage's
# text. Good enough for command_phrase()'s substring heuristic, which is all
# this ever feeds.
# --------------------------------------------------------------------------

__prometheus_shell_armed=0
__prometheus_shell_cmd=""
__prometheus_shell_start_ms=""

__prometheus_shell_preexec() {
    [[ $__prometheus_shell_armed == 1 ]] || return 0
    __prometheus_shell_armed=0
    __prometheus_shell_cmd=$BASH_COMMAND
    local t=${EPOCHREALTIME/./}
    __prometheus_shell_start_ms=${t:0:13}
}
trap '__prometheus_shell_preexec' DEBUG

__prometheus_shell_precmd() {
    local exit_code=$?
    local cmd=$__prometheus_shell_cmd
    local start_ms=$__prometheus_shell_start_ms

    if [[ -n $cmd && -n $start_ms ]]; then
        case $cmd in
            pr|"pr "*) ;;   # Mode B owns this event's narration already
            *)
                if __prometheus_enabled; then
                    local t=${EPOCHREALTIME/./}
                    local end_ms=${t:0:13}
                    local duration_ms=$(( end_ms - start_ms ))
                    (( duration_ms < 0 )) && duration_ms=0
                    # The extra { ; } 2>/dev/null isn't redundant with the
                    # command's own >/dev/null 2>&1: bash's job-control
                    # "[1] PID" notice is the *shell's* own stderr output for
                    # starting a background job, not the child's — printed
                    # even after `disown` (verified empirically) unless the
                    # whole background+disown sequence is grouped and its
                    # stderr redirected too. Without this, every narrated
                    # command would print a stray job line into the prompt.
                    { "$__PROMETHEUS_BIN_DIR/prometheus-shell" exit-code \
                        "$cmd" "$exit_code" "$duration_ms" >/dev/null 2>&1 & disown; } 2>/dev/null
                fi
                ;;
        esac
    fi

    __prometheus_shell_cmd=""
    __prometheus_shell_start_ms=""
    __prometheus_shell_armed=1
    return $exit_code
}
PROMPT_COMMAND+=(__prometheus_shell_precmd)

# --------------------------------------------------------------------------
# Mode B — pr, opt-in output summarization
# --------------------------------------------------------------------------

pr() {
    if [[ $# -eq 0 ]]; then
        echo "usage: pr <command> [args...]" >&2
        return 2
    fi

    local t=${EPOCHREALTIME/./}
    local start_ms=${t:0:13}

    mkdir -p "$__PROMETHEUS_RUN_DIR" 2>/dev/null
    local out_file
    if ! out_file=$(mktemp "$__PROMETHEUS_RUN_DIR/pr.XXXXXX" 2>/dev/null); then
        "$@"
        return $?
    fi

    # Interactive TUIs are explicitly out of scope (docs/05 Q2) — stdout
    # stops being a tty the moment it's piped through tee, which is exactly
    # the tradeoff that lets this sidestep real terminal capture entirely.
    "$@" 2>&1 | tee "$out_file"
    local exit_code=${PIPESTATUS[0]}

    t=${EPOCHREALTIME/./}
    local end_ms=${t:0:13}
    local duration_ms=$(( end_ms - start_ms ))
    (( duration_ms < 0 )) && duration_ms=0

    if __prometheus_enabled; then
        # See the matching comment in __prometheus_shell_precmd: the grouping
        # and stderr redirect suppress bash's own "[1] PID" job-start notice,
        # not just the child's output.
        { "$__PROMETHEUS_BIN_DIR/prometheus-shell" pr \
            "$*" "$exit_code" "$duration_ms" "$out_file" >/dev/null 2>&1 & disown; } 2>/dev/null
    else
        rm -f "$out_file"
    fi

    return $exit_code
}
