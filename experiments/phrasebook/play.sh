#!/usr/bin/env bash
# Play the staged phrase-bank review (Phase 2, task 2.10).
#
#   ./play.sh                 the session, in order — start here
#   ./play.sh all             every by-event sequence, one moment at a time
#   ./play.sh command_failed  one moment's sequence
#   ./play.sh --list          what's here, without playing it
#
# THIS MAKES SOUND. Nothing else in the review does.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ "${1:-}" == "--list" ]]; then
  echo "session:"
  ls session/*.wav 2>/dev/null | sed 's|^|  |'
  echo "by-event sequences:"
  ls by-event/*-all.wav 2>/dev/null | sed 's|^|  |'
  exit 0
fi

play() {
  echo "  $(basename "$1")"
  paplay --client-name=prometheus-review "$1"
}

case "${1:-session}" in
  session)
    echo "A plausible hour of work, in the order it would happen."
    echo "(Listen for: would you still want this on at the end of it?)"
    echo
    for f in session/[0-9][0-9]-*.wav; do
      [[ "$(basename "$f")" == 00-* ]] && continue
      play "$f"
      sleep 1.2
    done
    ;;
  all)
    for f in by-event/*-all.wav; do
      echo
      echo "== $(basename "$f" -all.wav)"
      play "$f"
      sleep 1.0
    done
    ;;
  *)
    f="by-event/$1-all.wav"
    [[ -f "$f" ]] || { echo "no such moment: $1" >&2; exit 1; }
    echo "== $1"
    play "$f"
    ;;
esac
