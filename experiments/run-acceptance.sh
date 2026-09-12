#!/usr/bin/env bash
# Runs the Phase 0 acceptance tests against a throwaway voxtype state dir, so
# the mic gate is exercised without writing to a live voxtype's real one.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAKE="$(mktemp -d -p "${XDG_RUNTIME_DIR:-/run/user/$UID}" prometheus-test.XXXXXX)"
echo idle > "$FAKE/state"   # not /tmp: the unit sets PrivateTmp=yes
cleanup() { rm -rf "$FAKE"; systemctl --user set-environment PROMETHEUS_VOXTYPE_DIR= 2>/dev/null || true; }
trap cleanup EXIT

systemctl --user set-environment PROMETHEUS_VOXTYPE_DIR="$FAKE"
systemctl --user restart prometheusd.service
sleep 0.5
PROMETHEUS_VOXTYPE_DIR="$FAKE" python3 "$REPO/experiments/acceptance-phase0.py"
rc=$?

systemctl --user unset-environment PROMETHEUS_VOXTYPE_DIR
systemctl --user restart prometheusd.service
exit $rc
