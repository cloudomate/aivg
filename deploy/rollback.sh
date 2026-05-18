#!/usr/bin/env bash
# Exact inverse of deploy-to-hermes.sh. Restores the production gateway to its
# pre-deployment state (FR-005 / SC-006): restore config.yaml backup byte-for-
# byte, remove the plugin dir, restart, verify pre-existing platforms intact.
set -euo pipefail

HOST="${HERMES_SSH:-hermes}"
HROOT="/home/ubuntu/.hermes/hermes-agent"
PLUGIN_DST="$HROOT/plugins/platforms/satellite_webrtc"
CFG="\$HOME/.hermes/config.yaml"
REPO_ROOT="$(git rev-parse --show-toplevel)"
STATE_DIR="$REPO_ROOT/deploy/.state"
ssh_h(){ ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" "$@"; }

BK="$(cat "$STATE_DIR/last_backup" 2>/dev/null || true)"
[ -n "$BK" ] || { echo "No recorded backup in $STATE_DIR/last_backup — cannot roll back safely"; exit 1; }

echo "🔒 Rolling back: restore ~/.hermes/$BK, remove $PLUGIN_DST, restart gateway."
if [ "${1:-}" != "--yes" ]; then
  read -r -p "Proceed? (yes/no) " a; [ "$a" = yes ] || { echo "Declined."; exit 3; }
fi

t0=$(date +%s)
ssh_h "test -s \"\$HOME/.hermes/$BK\"" || { echo "FAIL: backup ~/.hermes/$BK missing"; exit 1; }
ssh_h "cp \"\$HOME/.hermes/$BK\" \"$CFG\""                       # restore config
ssh_h "rm -rf \"$PLUGIN_DST\""                                   # remove plugin
ssh_h "~/.local/bin/hermes gateway restart" || ssh_h "~/.local/bin/hermes gateway status" || true

# Verify: config identical to backup, plugin gone, pre-existing platforms intact.
ssh_h "cmp -s \"$CFG\" \"\$HOME/.hermes/$BK\"" \
  && echo "OK: config.yaml restored byte-for-byte" \
  || { echo "FAIL: config.yaml differs from backup"; exit 1; }
ssh_h "test ! -e \"$PLUGIN_DST\"" && echo "OK: plugin dir removed" \
  || { echo "FAIL: plugin dir still present"; exit 1; }
if [ -f "$STATE_DIR/pre_platforms.txt" ]; then
  ssh_h "ls $HROOT/plugins/platforms" | sort > "$STATE_DIR/rollback_platforms.txt"
  cmp -s "$STATE_DIR/pre_platforms.txt" "$STATE_DIR/rollback_platforms.txt" \
    && echo "OK: pre-existing platforms == pre-deploy state (SC-005)" \
    || { echo "FAIL: platform set differs from pre-deploy"; exit 1; }
fi
echo "ROLLBACK OK in $(( $(date +%s) - t0 ))s (target <300s, SC-006)"
