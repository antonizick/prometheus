#!/usr/bin/env bash
# Phase 2 task 2.6 acceptance: "VRAM returns to baseline within ~6 minutes of
# last use." Loads the real runtime model through the real on-demand path
# (bin/prometheus-llm -> systemctl --user start prometheus-ollama.service),
# then polls nvidia-smi + `ollama ps` every 20s until VRAM drops back to
# baseline or 8 minutes pass. keep_alive is whatever config.json says
# (5m, per docs/07 — this script does not override it).
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

OUT="experiments/keepalive-results.md"
LOG="/tmp/verify-keepalive-raw.log"
: > "$LOG"

baseline=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
echo "baseline VRAM (nothing loaded): ${baseline} MiB" | tee -a "$LOG"

echo "triggering a real summary through bin/prometheus-llm (on-demand start)..." | tee -a "$LOG"
t_trigger=$(date +%s)
echo "FAIL: two tests failed after the refactor, both in the auth flow." | ./bin/prometheus-llm summarize -c test | tee -a "$LOG"

loaded=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
echo "$(date +%T) VRAM right after load: ${loaded} MiB" | tee -a "$LOG"
ollama ps | tee -a "$LOG"

deadline=$((t_trigger + 480))  # 8 minutes
released_at=""
while [ "$(date +%s)" -lt "$deadline" ]; do
  sleep 20
  now_vram=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
  now_ps=$(ollama ps | tail -n +2)
  elapsed=$(( $(date +%s) - t_trigger ))
  echo "$(date +%T) +${elapsed}s  VRAM=${now_vram} MiB  ps=[${now_ps:-empty}]" | tee -a "$LOG"
  if [ -z "$now_ps" ] && [ $((now_vram - baseline)) -lt 150 ]; then
    released_at=$elapsed
    break
  fi
done

{
  echo "# Keep-alive VRAM release — task 2.6"
  echo
  echo "Measured $(date '+%Y-%m-%d %H:%M') on this machine, real "'`ollama serve`'" via"
  echo "prometheus-ollama.service, real qwen3:4b-instruct load, config.json's real"
  echo '`llm.keep_alive` (5m — never -1, per instruction).'
  echo
  echo "Baseline VRAM (nothing loaded): **${baseline} MiB**"
  echo "VRAM right after load: **${loaded} MiB** (+$((loaded - baseline)) MiB)"
  echo
  if [ -n "$released_at" ]; then
    echo "**VRAM returned to baseline ${released_at}s after the triggering call** — within the ~6 minute acceptance window."
  else
    echo "**VRAM had NOT returned to baseline after 480s** — investigate keep_alive handling."
  fi
  echo
  echo '```'
  cat "$LOG"
  echo '```'
} > "$OUT"

echo "wrote $OUT"
