#!/usr/bin/env bash
# Install Prometheus Phase 0 into the user session.
#
# Symlinks rather than copies: editing the repo takes effect immediately, which
# is what we want while the thing is still being built.
#
#   ./install.sh            # install / refresh
#   ./install.sh --uninstall
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/prometheus"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/prometheus"
# prometheus-attention is a library, not a command — prometheus-hypr and
# experiments/replay-scoring.py both import it from the repo by path, which is
# what keeps the live scoring and the replay harness provably identical. It is
# deliberately not symlinked into BIN_DIR: there is nothing to run.
BINARIES=(prometheusd prometheus prometheus-toggle prometheus-boot prometheus-hypr prometheus-llm prometheus-phrasebank prometheus-claude prometheus-shell)
UNITS=(prometheus.target prometheusd.service prometheus-boot.service prometheus-hypr.service prometheus-ollama.service)

if [[ "${1:-}" == "--uninstall" ]]; then
  systemctl --user stop prometheus.target prometheus-ollama.service 2>/dev/null || true
  systemctl --user disable prometheus-boot.service prometheusd.service prometheus-hypr.service 2>/dev/null || true
  for b in "${BINARIES[@]}"; do rm -f "$BIN_DIR/$b"; done
  for u in "${UNITS[@]}"; do rm -f "$UNIT_DIR/$u"; done
  systemctl --user daemon-reload
  echo "Uninstalled. Config in $CONFIG_DIR and state in $STATE_DIR were left alone."
  exit 0
fi

mkdir -p "$BIN_DIR" "$UNIT_DIR" "$CONFIG_DIR" "$STATE_DIR"

echo "==> binaries -> $BIN_DIR"
for b in "${BINARIES[@]}"; do
  ln -sfn "$REPO/bin/$b" "$BIN_DIR/$b"
  echo "    $b"
done

echo "==> units -> $UNIT_DIR"
for u in "${UNITS[@]}"; do
  # %h expansion assumes the repo lives at ~/Work/prometheus; rewrite if not.
  sed "s|%h/Work/prometheus|$REPO|g" "$REPO/systemd/$u" > "$UNIT_DIR/$u"
  echo "    $u"
done

echo "==> config -> $CONFIG_DIR"
for f in config.json persona.md about-me.md phrasebank-spec.json; do
  if [[ -e "$CONFIG_DIR/$f" ]]; then
    echo "    $f (kept — yours)"
  else
    cp "$REPO/config/$f" "$CONFIG_DIR/$f"
    echo "    $f (installed)"
  fi
done

[[ -e "$STATE_DIR/enabled" ]]   || echo 0      > "$STATE_DIR/enabled"
[[ -e "$STATE_DIR/verbosity" ]] || echo normal > "$STATE_DIR/verbosity"

echo "==> Claude Code hooks -> ~/.claude/settings.json"
CLAUDE_SETTINGS="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json"
HOOK_CMD="$BIN_DIR/prometheus-claude"
if command -v jq >/dev/null; then
  [[ -e "$CLAUDE_SETTINGS" ]] || echo '{}' > "$CLAUDE_SETTINGS"
  if jq -e --arg cmd "$HOOK_CMD" \
      '[(.hooks.Stop // [])[].hooks[]?.command] | index($cmd)' \
      "$CLAUDE_SETTINGS" >/dev/null 2>&1; then
    echo "    already registered (kept — yours)"
  else
    cp "$CLAUDE_SETTINGS" "$CLAUDE_SETTINGS.prometheus-bak-$(date +%Y%m%d%H%M%S)"
    tmp="$(mktemp)"
    jq --arg cmd "$HOOK_CMD" '
      .hooks = (.hooks // {}) |
      .hooks.Stop = ((.hooks.Stop // []) + [{"matcher":"","hooks":[{"type":"command","command":$cmd,"async":true,"timeout":20}]}]) |
      .hooks.Notification = ((.hooks.Notification // []) + [{"matcher":"","hooks":[{"type":"command","command":$cmd,"async":true,"timeout":20}]}])
    ' "$CLAUDE_SETTINGS" > "$tmp" && mv "$tmp" "$CLAUDE_SETTINGS"
    echo "    registered Stop + Notification (backup saved alongside settings.json)"
  fi
else
  echo "    jq not found — skipped; wire manually, see docs/01-architecture.md"
fi

echo "==> shell integration -> ~/.bashrc"
BASHRC="$HOME/.bashrc"
SOURCE_LINE="source \"$REPO/shell/prometheus.bash\""
if [[ -f "$BASHRC" ]] && grep -qF "$SOURCE_LINE" "$BASHRC"; then
  echo "    already wired (kept — yours)"
elif [[ -f "$BASHRC" ]]; then
  cp "$BASHRC" "$BASHRC.prometheus-bak-$(date +%Y%m%d%H%M%S)"
  {
    echo ""
    echo "# Prometheus shell integration (Phase 4) — see shell/prometheus.bash"
    echo "$SOURCE_LINE"
  } >> "$BASHRC"
  echo "    added (backup saved alongside .bashrc; open a new shell to pick it up)"
else
  echo "    no ~/.bashrc found — skipped; add manually: $SOURCE_LINE"
fi

systemctl --user daemon-reload
systemctl --user enable prometheusd.service >/dev/null      # WantedBy=prometheus.target
systemctl --user enable prometheus-hypr.service >/dev/null  # WantedBy=prometheus.target
systemctl --user enable prometheus-boot.service >/dev/null
# prometheus-ollama.service has no [Install] section on purpose — it must
# NOT start with prometheus.target (docs/07: GPU stays free while idle).
# bin/prometheus-llm starts it on demand with `systemctl --user start`.

cat <<EOF

Installed.

  prometheus on            power on   (starts the units)
  prometheus off           power off  (stops every process, frees VRAM)
  prometheus say "hello"   speak something
  prometheus status        what's running and what it costs
  prometheus regenerate    write the phrase bank (offline, a few minutes)
  prometheus phrase --show what it has to say, and how many ways
  pr make test             opt-in: run + summarize a command's output

Open a new shell (or \`source ~/.bashrc\`) to pick up the shell integration.
Add the keybinds:   see $REPO/README.md
EOF

# Phase 5 (task 5.5) rewrote these to submit intents instead of spawning their
# own Piper, so that only one thing ever holds the audio device (ADR-0001).
# They are Omarchy's, not ours — this installer does not own or replace them —
# but they now reference `prometheus`, so say so rather than leaving it to be
# discovered. Each falls back to its original direct-Piper path when the broker
# socket is absent, so an uninstall degrades them rather than breaking them.
for legacy in omarchy-tts-read-cursor omarchy-tts-terminal-live; do
  if [[ -e "$BIN_DIR/$legacy" ]] && grep -q 'prometheus say' "$BIN_DIR/$legacy" 2>/dev/null; then
    echo "Note: $legacy routes speech through the broker."
    echo "      Original preserved at $BIN_DIR/$legacy.pre-prometheus.bak"
  fi
done
