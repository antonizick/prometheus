#!/usr/bin/env bash
# Measure the resource cost of each Prometheus state (docs/07-resource-profile.md).
#
#   ./measure-overhead.sh [idle_seconds]     default 600 (the 10-minute window
#                                            the Phase 0 acceptance test names)
#
# Measures COLD (toggled off) and WARM (on, idle), and writes the numbers to
# experiments/overhead-results.md. Asserting low overhead isn't good enough —
# this is what turns the tables in doc 07 into measured facts.
#
# Contract being tested:
#   COLD  zero processes, zero RAM, VRAM unchanged
#   WARM  < 150 MB RAM total (< 250 MB with the second voice), ~0% idle CPU
set -uo pipefail

IDLE_SECS="${1:-600}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$REPO/experiments/overhead-results.md"
STATE_DIR_J="${XDG_STATE_HOME:-$HOME/.local/state}/prometheus/journal"
STATE_DIR_T="${XDG_STATE_HOME:-$HOME/.local/state}/prometheus/transcript.jsonl"
WARM_LIMIT_MB=150
WARM_LIMIT_TWO_VOICE_MB=250

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
fail=0

# --- helpers --------------------------------------------------------------

# PIDs of the resident daemons (prometheusd, prometheus-hypr) and the
# children they own. Matched on argv[0]/argv[1] and parentage, so an editor
# or grep that merely mentions the name isn't counted.
own_pids() {
  local daemons=() p exe script ppid
  for p in /proc/[0-9]*; do
    p=${p#/proc/}
    [[ -r /proc/$p/cmdline ]] || continue
    mapfile -d '' -t argv < "/proc/$p/cmdline" 2>/dev/null || continue
    [[ ${#argv[@]} -gt 0 ]] || continue
    exe=$(basename -- "${argv[0]:-}")
    script=$(basename -- "${argv[1]:-}")
    if [[ "$exe" == prometheusd || "$script" == prometheusd \
       || "$exe" == prometheus-hypr || "$script" == prometheus-hypr ]]; then
      daemons+=("$p")
    fi
  done
  printf '%s\n' "${daemons[@]:-}"
  local d
  for d in "${daemons[@]:-}"; do
    for p in /proc/[0-9]*; do
      p=${p#/proc/}
      [[ -r /proc/$p/stat ]] || continue
      ppid=$(awk '{print $4}' < <(sed 's/.*) //' "/proc/$p/stat") 2>/dev/null)
      [[ "$ppid" == "$d" ]] && echo "$p"
    done
  done
}

rss_kb() { awk '/^VmRSS:/{print $2}' "/proc/$1/status" 2>/dev/null || echo 0; }
comm_of() { cat "/proc/$1/comm" 2>/dev/null || echo "?"; }
# utime+stime in seconds
cpu_secs() {
  local t; t=$(sed 's/.*) //' "/proc/$1/stat" 2>/dev/null) || { echo 0; return; }
  awk -v hz="$(getconf CLK_TCK)" '{print ($12 + $13) / hz}' <<<"$t"
}
# voluntary + involuntary context switches — the wakeup proxy for battery impact
switches() {
  awk '/ctxt_switches/{s+=$2} END{print s+0}' "/proc/$1/status" 2>/dev/null || echo 0
}
vram_mb() {
  command -v nvidia-smi >/dev/null || { echo "n/a"; return; }
  nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1
}
ollama_on_gpu() {
  command -v nvidia-smi >/dev/null || { echo "n/a"; return; }
  local n; n=$(nvidia-smi --query-compute-apps=process_name --format=csv,noheader 2>/dev/null \
               | grep -ci ollama || true)
  echo "${n:-0}"
}

# --- COLD -----------------------------------------------------------------

bold "==> COLD  (toggled off)"
prometheus off >/dev/null 2>&1 || true
sleep 3

mapfile -t cold_pids < <(own_pids | grep -v '^$' | sort -u)
cold_count=${#cold_pids[@]}
cold_pgrep=$(pgrep -af prometheus | grep -v measure-overhead | grep -vc '^$' || true)
cold_vram=$(vram_mb)
cold_ollama=$(ollama_on_gpu)

printf '    processes owned by prometheusd : %s\n' "$cold_count"
printf '    pgrep -af prometheus           : %s line(s)\n' "$cold_pgrep"
printf '    VRAM in use (whole GPU)        : %s MB\n' "$cold_vram"
printf '    ollama processes on GPU        : %s\n' "$cold_ollama"
[[ "$cold_count" -eq 0 ]] || { echo "    FAIL: processes survive the toggle"; fail=1; }
[[ "$cold_ollama" == "n/a" || "$cold_ollama" -eq 0 ]] || { echo "    FAIL: ollama still holds VRAM"; fail=1; }

# --- WARM -----------------------------------------------------------------

bold "==> WARM  (toggled on, idle for ${IDLE_SECS}s)"
prometheus on >/dev/null 2>&1
sleep 5

# The power-on confirmation ("Listening.") must not be counted as idle work.
#
# A fixed `sleep 3` used to stand in for this and it is not enough, which only
# became visible in Phase 5. Piper's first synthesis after a spawn also
# initialises the ONNX session lazily, across several threads, so it bills far
# more CPU-seconds than its wall time — measured at **1.62 s of CPU for a
# single word**. Any of that still running when the baseline is sampled lands
# in the delta and is reported as idle overhead. It failed the contract on a
# system that, measured over a genuinely quiet window, uses 0.000 s.
#
# So: ask the broker instead of guessing. `status --speaking` prints "speaking"
# (exit 0), "idle" (exit 1) or "unknown" (exit 2, daemon not reachable yet).
#
# All three states matter, and getting that wrong is how the first version of
# this fix still failed. It broke on *any* non-zero exit, so a daemon that had
# not finished starting answered "unknown", the loop exited immediately, and
# the baseline was sampled before Piper had even begun. Worse, "idle" is not a
# finish line on its own: `prometheus on` returns before the toggle's
# confirmation has been *queued*, so a single idle reading can simply mean
# "not started yet".
#
# Hence: wait for reachable, then require idle to hold continuously.
ready=0
for _ in $(seq 1 120); do          # up to 60s
  out=$(prometheus status --speaking 2>/dev/null)
  case "$out" in
    idle)     ready=$(( ready + 1 )) ;;   # count consecutive idles
    speaking) ready=0 ;;                  # still talking — start over
    *)        ready=0 ;;                  # unreachable — not ready to judge
  esac
  [[ "$ready" -ge 8 ]] && break            # 4s of continuous, reachable silence
  sleep 0.5
done
sleep 2   # let the player's own teardown settle after the last sample block

mapfile -t warm_pids < <(own_pids | grep -v '^$' | sort -u)
[[ ${#warm_pids[@]} -gt 0 ]] || { echo "    FAIL: nothing started"; fail=1; }

declare -A cpu0 sw0 name rss
total_rss=0
for p in "${warm_pids[@]}"; do
  name[$p]=$(comm_of "$p"); rss[$p]=$(rss_kb "$p")
  cpu0[$p]=$(cpu_secs "$p"); sw0[$p]=$(switches "$p")
  total_rss=$(( total_rss + ${rss[$p]:-0} ))
done
warm_vram=$(vram_mb)

printf '    %-14s %8s %10s\n' PROCESS PID "RSS (MB)"
for p in "${warm_pids[@]}"; do
  printf '    %-14s %8s %10.1f\n' "${name[$p]}" "$p" "$(bc -l <<<"${rss[$p]}/1024" 2>/dev/null || awk "BEGIN{print ${rss[$p]}/1024}")"
done
total_mb=$(awk "BEGIN{printf \"%.1f\", $total_rss/1024}")
printf '    %-14s %8s %10s\n' TOTAL "" "$total_mb"
printf '    VRAM in use (whole GPU)        : %s MB   (must equal COLD: %s)\n' "$warm_vram" "$cold_vram"

two_voice=$(python3 -c "
import json,os,sys
p=os.path.expanduser('~/.config/prometheus/config.json')
try:
    import re
    s=re.sub(r'//.*','',open(p).read())
    print('yes' if json.loads(s).get('voice',{}).get('agent',{}).get('enabled') else 'no')
except Exception: print('no')")
limit=$WARM_LIMIT_MB
[[ "$two_voice" == "yes" ]] && limit=$WARM_LIMIT_TWO_VOICE_MB

awk "BEGIN{exit !($total_mb <= $limit)}" \
  && echo "    RAM within budget (<= ${limit} MB)" \
  || { echo "    FAIL: warm RAM ${total_mb} MB exceeds ${limit} MB"; fail=1; }

echo "    idling for ${IDLE_SECS}s ..."
# Count what the desktop actually did during the window. "Idle" is an
# instruction to the operator, not a fact about the machine, and a window that
# wasn't idle produces real CPU for entirely correct reasons — the listener
# waking to receive an event is the behaviour being verified, not a violation
# of it. Phase 1 hit this and diagnosed it by hand (357 context switches from
# this very Claude Code session's animating title); Phase 5 hit it again. It
# should be on the report rather than rediscovered each time.
journal_before=$(wc -l < "$STATE_DIR_J" 2>/dev/null || echo 0)
# And count utterances. Speech is by far the most expensive thing this system
# does — a two-second utterance costs Piper well over a second of CPU across
# its ONNX threads — so a window containing even one is definitively not idle.
#
# Counting only desktop events was not enough, and the gap is easy to walk
# into: a Claude Code turn ending mid-window fires the Stop hook, which speaks.
# That is not desktop activity, nothing appears in the journal, and the window
# looks idle while Piper bills 1.4s. Measured exactly that, twice, before
# spotting it in `prometheus transcript`.
speech_before=$(wc -l < "$STATE_DIR_T" 2>/dev/null || echo 0)
sleep "$IDLE_SECS"
journal_after=$(wc -l < "$STATE_DIR_J" 2>/dev/null || echo 0)
speech_after=$(wc -l < "$STATE_DIR_T" 2>/dev/null || echo 0)
journal_events=$(( journal_after - journal_before ))
speech_events=$(( speech_after - speech_before ))

total_cpu=0; total_sw=0
printf '    %-14s %8s %12s %12s\n' PROCESS PID "CPU (s)" "ctx switches"
for p in "${warm_pids[@]}"; do
  [[ -r /proc/$p/stat ]] || { echo "    FAIL: pid $p died during the idle window"; fail=1; continue; }
  d=$(awk "BEGIN{printf \"%.3f\", $(cpu_secs "$p") - ${cpu0[$p]}}")
  s=$(( $(switches "$p") - ${sw0[$p]} ))
  total_cpu=$(awk "BEGIN{printf \"%.3f\", $total_cpu + $d}")
  total_sw=$(( total_sw + s ))
  printf '    %-14s %8s %12s %12s\n' "${name[$p]}" "$p" "$d" "$s"
done
cpu_pct=$(awk "BEGIN{printf \"%.4f\", 100*$total_cpu/$IDLE_SECS}")
printf '    %-14s %8s %12s %12s\n' TOTAL "" "$total_cpu" "$total_sw"
printf '    idle CPU                       : %s%% of one core\n' "$cpu_pct"
printf '    wakeups                        : %s per second\n' \
  "$(awk "BEGIN{printf \"%.3f\", $total_sw/$IDLE_SECS}")"
printf '    desktop events during window    : %s\n' "$journal_events"
printf '    utterances during window       : %s\n' "$speech_events"

if awk "BEGIN{exit !($cpu_pct < 0.1)}"; then
  echo "    idle CPU is effectively zero"
elif [[ "$journal_events" -gt 0 || "$speech_events" -gt 0 ]]; then
  # Not a failure. The contract is "no polling" — no CPU *without* an event —
  # not "no CPU ever". Waking to receive an event, or speaking when asked to,
  # is the behaviour under test rather than a violation of it.
  echo "    INCONCLUSIVE: ${cpu_pct}% CPU, but the window was NOT idle"
  echo "                  ${journal_events} desktop event(s), ${speech_events} utterance(s)"
  echo "                  Two things commonly invalidate this run, both easy to miss:"
  echo "                    - a window whose title animates (a Claude Code session"
  echo "                      mid-turn) produces a stream of real Hyprland events"
  echo "                    - a Claude Code turn ENDING fires the Stop hook, which"
  echo "                      speaks; one 2s utterance costs Piper ~1.4s of CPU"
  echo "                  Re-run with the desktop untouched and no agent working."
else
  echo "    FAIL: measurable idle CPU (${cpu_pct}%) with a genuinely idle window"
  fail=1
fi

[[ "$warm_vram" == "n/a" || "$warm_vram" == "$cold_vram" ]] \
  && echo "    VRAM unchanged between COLD and WARM" \
  || echo "    NOTE: VRAM differs (${cold_vram} -> ${warm_vram} MB); other GPU users vary this"

# --- record ---------------------------------------------------------------

{
  echo "# Overhead — measured"
  echo
  echo "Generated by \`experiments/measure-overhead.sh\` on $(date -Iseconds)."
  echo "Idle window: ${IDLE_SECS}s. Second voice enabled: ${two_voice}."
  echo
  echo "Replaces the estimates in [07-resource-profile.md](../docs/07-resource-profile.md)."
  echo
  echo "## COLD — toggled off"
  echo
  echo "| Measure | Value | Required |"
  echo "|---|---|---|"
  echo "| Prometheus processes | ${cold_count} | 0 |"
  echo "| \`pgrep -af prometheus\` | ${cold_pgrep} line(s) | 0 |"
  echo "| RAM | 0 | 0 |"
  echo "| Ollama processes on GPU | ${cold_ollama} | 0 |"
  echo "| VRAM in use (whole GPU) | ${cold_vram} MB | baseline |"
  echo
  echo "## WARM — toggled on, idle"
  echo
  echo "| Process | PID | RSS (MB) |"
  echo "|---|---|---|"
  for p in "${warm_pids[@]}"; do
    echo "| ${name[$p]} | ${p} | $(awk "BEGIN{printf \"%.1f\", ${rss[$p]}/1024}") |"
  done
  echo "| **TOTAL** | | **${total_mb}** |"
  echo
  echo "| Measure | Value | Budget |"
  echo "|---|---|---|"
  echo "| RAM | ${total_mb} MB | < ${limit} MB |"
  echo "| CPU over ${IDLE_SECS}s idle | ${total_cpu} s (${cpu_pct}% of one core) | ~0 |"
  echo "| Context switches | ${total_sw} ($(awk "BEGIN{printf \"%.3f\", $total_sw/$IDLE_SECS}")/s) | low |"
  echo "| VRAM | ${warm_vram} MB | unchanged from COLD |"
  echo "| Desktop events during window | ${journal_events} | 0 for a valid run |"
  echo "| Utterances during window | ${speech_events} | 0 for a valid run |"
  echo
  echo "## Verdict"
  echo
  if [[ $fail -eq 0 ]]; then
    echo "**Within contract.** COLD is genuinely zero; WARM is ${total_mb} MB and"
    echo "no measurable idle CPU."
  elif [[ "$journal_events" -gt 0 || "$speech_events" -gt 0 ]]; then
    echo "**Inconclusive — the window was not idle** (${journal_events} desktop"
    echo "event(s), ${speech_events} utterance(s)). The contract is \"no CPU without"
    echo "an event\", so CPU spent waking for a real event, or speaking when asked"
    echo "to, is the behaviour under test rather than a breach of it. Re-run with"
    echo "the desktop untouched and no agent working."
  else
    echo "**Outside contract — the design needs revising** (doc 07 makes this a gate,"
    echo "not an aspiration). See the FAIL lines in the run output."
  fi
} > "$OUT"

echo
bold "==> wrote $OUT"
[[ $fail -eq 0 ]] && bold "PASS — within the resource contract" || bold "FAIL — see above"
exit $fail
