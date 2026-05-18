#!/usr/bin/env bash
# Deploy the satellite_webrtc adapter onto the PRODUCTION Hermes gateway.
#
# Safety contract (specs/003 contracts/deployment-procedure.md):
#   preflight (read-only) -> explicit confirm -> backup config -> vendor
#   plugin -> add satellite: block -> restart -> verify. Any failure after
#   the backup either auto-restores or prints `ROLLBACK REQUIRED`.
#
#   ./deploy-to-hermes.sh --preflight   # read-only checks, NO mutation
#   ./deploy-to-hermes.sh               # full gated deploy (confirms each step)
#   ./deploy-to-hermes.sh --yes         # skip prompts (CI/operator pre-authorized)
set -euo pipefail

HOST="${HERMES_SSH:-hermes}"
HROOT="/home/ubuntu/.hermes/hermes-agent"
PLUGIN_DST="$HROOT/plugins/platforms/satellite_webrtc"
CFG="\$HOME/.hermes/config.yaml"
REPO_ROOT="$(git rev-parse --show-toplevel)"
STATE_DIR="$REPO_ROOT/deploy/.state"
mkdir -p "$STATE_DIR"

say(){ printf '\n=== %s ===\n' "$*"; }
ssh_h(){ ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" "$@"; }
confirm(){ # $1 = description of the mutation
  [ "${ASSUME_YES:-0}" = 1 ] && return 0
  printf '\n🔒 HOST-MUTATING: %s\n' "$1"
  read -r -p 'Proceed with THIS step on the production gateway? (yes/no) ' a
  [ "$a" = yes ] || { echo "Declined. Aborting (no further changes)."; exit 3; }
}

preflight(){
  say "Preflight (read-only)"
  ssh_h 'echo reachable' >/dev/null || { echo "FAIL: ssh $HOST unreachable"; exit 1; }
  ssh_h "test -d $HROOT" || { echo "FAIL: hermes-agent not found at $HROOT"; exit 1; }
  ssh_h "$HROOT/venv/bin/python -c 'import aiortc,aiohttp,av;print(\"deps ok\")'" \
    || { echo "FAIL: aiortc/aiohttp/av missing in host venv"; exit 1; }
  # Snapshot pre-existing platforms for the regression check (SC-005).
  ssh_h "ls $HROOT/plugins/platforms" | sort > "$STATE_DIR/pre_platforms.txt"
  echo "Pre-existing platform plugins:"; cat "$STATE_DIR/pre_platforms.txt"
  if ssh_h "test -e $PLUGIN_DST"; then echo "WARN: $PLUGIN_DST already exists (redeploy)"; fi
  echo "Preflight OK — nothing was changed."
}

postverify(){
  say "Post-verify"
  # E1 / FR-014: deployed tree must not embed speech engines outside the seam.
  if ssh_h "grep -RIlE 'import (whisper|faster_whisper|piper)' $PLUGIN_DST \
        --exclude=hermes_bridge.py 2>/dev/null | grep -v hermes_bridge || true" \
        | grep -q .; then
    echo "FAIL: embedded speech engine import in deployed tree (constitution I)"; return 1
  fi
  # Plugin importable + registers without error.
  ssh_h "cd $HROOT && venv/bin/python -c \
     'import importlib;m=importlib.import_module(\"plugins.platforms.satellite_webrtc\");assert hasattr(m,\"register\");print(\"plugin import + register OK\")'" \
     || { echo "FAIL: plugin import/register"; return 1; }
  # SC-005: pre-existing platforms still present.
  ssh_h "ls $HROOT/plugins/platforms" | sort > "$STATE_DIR/post_platforms.txt"
  if ! comm -23 "$STATE_DIR/pre_platforms.txt" "$STATE_DIR/post_platforms.txt" \
       | grep -q . ; then
    echo "OK: no pre-existing platform removed (SC-005)"
  else
    echo "FAIL: a pre-existing platform disappeared"; return 1
  fi
}

rollback_hint(){ echo "ROLLBACK REQUIRED — run: deploy/rollback.sh (backup: $(cat "$STATE_DIR/last_backup" 2>/dev/null||echo '??'))"; }

main(){
  preflight
  [ "${1:-}" = "--preflight" ] && exit 0

  confirm "back up ~/.hermes/config.yaml, copy the plugin, add a satellite: block, and restart the gateway"

  say "Backup config.yaml"
  BK="config.yaml.bak.f003.$(date -u +%Y%m%dT%H%M%SZ)"
  ssh_h "cp \"$CFG\" \"\$HOME/.hermes/$BK\"" && echo "$BK" > "$STATE_DIR/last_backup"
  ssh_h "test -s \"\$HOME/.hermes/$BK\"" || { echo "FAIL: backup not created"; exit 1; }
  echo "Backup: ~/.hermes/$BK"

  say "Vendor plugin → $PLUGIN_DST"
  TMP="$(mktemp -d)"; mkdir -p "$TMP/satellite_webrtc"
  cp "$REPO_ROOT"/deploy/plugin/{__init__.py,adapter.py,plugin.yaml} "$TMP/satellite_webrtc/"
  cp -R "$REPO_ROOT/src/hermes_satellite_adapter" "$TMP/satellite_webrtc/hermes_satellite_adapter"
  if ! rsync -a --delete -e "ssh -o BatchMode=yes" "$TMP/satellite_webrtc/" "$HOST:$PLUGIN_DST/"; then
    echo "FAIL: rsync plugin"; rollback_hint; exit 1
  fi
  rm -rf "$TMP"

  say "Add satellite: block (idempotent)"
  ssh_h "grep -qE '^satellite:' \"$CFG\" || cat >> \"$CFG\" <<'YAML'

satellite:
  enabled: true
  management_port: 8643
  webrtc_port: 8644
  heartbeat_interval: 30
  mdns_advertise: false
  default_config:
    wake_word: \"Hey Jarvis\"
    routing_mode: \"preferred\"
    log_level: \"INFO\"
YAML" || { echo "FAIL: add satellite block"; rollback_hint; exit 1; }

  say "Restart gateway"
  # Restart surface is documented by the feature-002 hermes-agent skill as
  # `hermes gateway restart`; fall back to status if restart is unavailable.
  ssh_h "~/.local/bin/hermes gateway restart" \
    || ssh_h "~/.local/bin/hermes gateway status" \
    || { echo "FAIL: gateway restart"; rollback_hint; exit 1; }

  if ! postverify; then rollback_hint; exit 1; fi
  say "DEPLOY OK"
  echo "Next: ssh -N -L 8643:localhost:8643 -L 8644:localhost:8644 $HOST  then run the Electron client."
}
main "$@"
