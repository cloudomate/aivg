#!/usr/bin/env bash
# Deploy the satellite_webrtc adapter onto the LOCAL Hermes install on this
# machine (no ssh, no LAN, no tunnel — all localhost, so WebRTC media works).
#
# Mirrors deploy/deploy-to-hermes.sh's safety contract (backup-first ->
# vendor -> satellite: block -> restart -> verify) but against local paths.
# The production ssh script is left UNCHANGED (FR-010).
#
#   ./deploy-local.sh --preflight   # read-only checks, NO mutation
#   ./deploy-local.sh               # gated local deploy
#   ./deploy-local.sh --yes         # skip the confirm prompt
set -euo pipefail

HROOT="$HOME/.hermes/hermes-agent"
VENVPY="$HROOT/venv/bin/python"
PLUGIN_DST="$HROOT/plugins/platforms/satellite_webrtc"
CFG="$HOME/.hermes/config.yaml"
REPO_ROOT="$(git rev-parse --show-toplevel)"
STATE_DIR="$REPO_ROOT/deploy/.state"
mkdir -p "$STATE_DIR"

say(){ printf '\n=== %s ===\n' "$*"; }
confirm(){
  [ "${ASSUME_YES:-0}" = 1 ] && return 0
  printf '\n🔒 LOCAL-MUTATING: %s\n' "$1"
  read -r -p 'Proceed on the LOCAL Hermes install? (yes/no) ' a
  [ "$a" = yes ] || { echo "Declined. Aborting (no changes)."; exit 3; }
}

preflight(){
  say "Preflight (read-only)"
  [ -d "$HROOT" ] || { echo "FAIL: local hermes-agent not at $HROOT"; exit 1; }
  [ -f "$CFG" ]   || { echo "FAIL: local config not at $CFG"; exit 1; }
  "$VENVPY" -c 'import aiohttp,av;print("aiohttp+av ok")' \
    || { echo "FAIL: aiohttp/av missing in local venv"; exit 1; }
  if "$VENVPY" -c 'import aiortc' 2>/dev/null; then
    echo "aiortc present"
  else
    echo "aiortc MISSING — deploy step will install it via uv"
  fi
  ls "$HROOT/plugins/platforms" 2>/dev/null | sort > "$STATE_DIR/pre_platforms_local.txt" || true
  echo "Pre-existing platform plugins:"; cat "$STATE_DIR/pre_platforms_local.txt" 2>/dev/null || echo "(none)"
  [ -e "$PLUGIN_DST" ] && echo "WARN: $PLUGIN_DST exists (redeploy)"
  echo "Preflight OK — nothing was changed."
}

postverify(){
  say "Post-verify"
  if grep -RIlE 'import (whisper|faster_whisper|piper)' "$PLUGIN_DST" 2>/dev/null \
       | grep -v hermes_bridge.py | grep -q .; then
    echo "FAIL: embedded speech engine import (constitution I)"; return 1
  fi
  ( cd "$HROOT" && "$VENVPY" -c \
     'import importlib;m=importlib.import_module("plugins.platforms.satellite_webrtc");assert hasattr(m,"register");print("plugin import + register OK")' ) \
     || { echo "FAIL: plugin import/register"; return 1; }
  ls "$HROOT/plugins/platforms" | sort > "$STATE_DIR/post_platforms_local.txt"
  if comm -23 "$STATE_DIR/pre_platforms_local.txt" "$STATE_DIR/post_platforms_local.txt" | grep -q .; then
    echo "FAIL: a pre-existing platform disappeared"; return 1
  fi
  echo "OK: no pre-existing platform removed"
  LP=""
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    LP="$(lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null \
          | grep -Eo ':(8643|8644)\b' | sort -u | tr -d ':' | tr '\n' ' ')"
    [ "$LP" = "8643 8644 " ] && break
    sleep 2
  done
  if [ "$LP" = "8643 8644 " ]; then
    echo "OK: control(8643) AND signaling(8644) both LISTENING"
  else
    echo "FAIL: both planes not listening — got: [$LP]"; return 1
  fi
}

main(){
  for a in "$@"; do [ "$a" = "--yes" ] && ASSUME_YES=1; done
  preflight
  [ "${1:-}" = "--preflight" ] && exit 0
  confirm "back up config.yaml, install aiortc (if missing), vendor the plugin, add the satellite: block + cli streaming override, and restart the local gateway"

  say "Backup config.yaml"
  BK="config.yaml.bak.f007local.$(date -u +%Y%m%dT%H%M%SZ)"
  cp "$CFG" "$HOME/.hermes/$BK"; echo "$BK" > "$STATE_DIR/last_backup_local"
  [ -s "$HOME/.hermes/$BK" ] || { echo "FAIL: backup not created"; exit 1; }
  echo "Backup: ~/.hermes/$BK"

  say "Ensure aiortc in local venv"
  if "$VENVPY" -c 'import aiortc' 2>/dev/null; then
    echo "aiortc already present"
  else
    uv pip install --python "$VENVPY" aiortc \
      || { echo "FAIL: uv pip install aiortc"; exit 1; }
    "$VENVPY" -c 'import aiortc;print("aiortc installed")' \
      || { echo "FAIL: aiortc still not importable"; exit 1; }
  fi

  say "Vendor plugin → $PLUGIN_DST"
  TMP="$(mktemp -d)"; mkdir -p "$TMP/satellite_webrtc"
  cp "$REPO_ROOT"/deploy/plugin/{__init__.py,adapter.py,plugin.yaml} "$TMP/satellite_webrtc/"
  cp -R "$REPO_ROOT/src/hermes_satellite_adapter" "$TMP/satellite_webrtc/hermes_satellite_adapter"
  mkdir -p "$PLUGIN_DST"
  rsync -a --delete "$TMP/satellite_webrtc/" "$PLUGIN_DST/" \
    || { echo "FAIL: vendor plugin"; exit 1; }
  rm -rf "$TMP"

  say "Add satellite: block (idempotent)"
  if ! grep -qE '^satellite:' "$CFG"; then
    cat >> "$CFG" <<'YAML'

satellite:
  enabled: true
  management_port: 8643
  webrtc_port: 8644
  heartbeat_interval: 30
  mdns_advertise: false
  default_config:
    wake_word: "Hey Jarvis"
    routing_mode: "preferred"
    log_level: "INFO"
YAML
    echo "satellite: block added"
  else
    echo "satellite: block already present (skip)"
  fi

  say "Enable gateway streaming for the satellite (display.platforms.cli)"
  # Per-platform enable gate (resolve_display_setting step 1). Necessary but
  # NOT sufficient on its own — the draft-vs-edit TRANSPORT is global-only
  # (see next step). Kept for clarity/robustness.
  if grep -qE '^  platforms: \{\}$' "$CFG"; then
    perl -0pi -e 's/^  platforms: \{\}$/  platforms:\n    cli:\n      streaming: true/m' "$CFG"
    echo "display.platforms.cli.streaming: true set"
  elif grep -qE '^    cli:$' "$CFG" && grep -qE '^      streaming: true$' "$CFG"; then
    echo "cli streaming override already present (skip)"
  else
    echo "WARN: display.platforms not empty and cli override absent — set it manually:"
    echo "      display.platforms.cli.streaming: true"
  fi

  say "Set top-level streaming block (enabled:true, transport:auto)"
  # The native-draft-vs-edit selector is governed ONLY by the global
  # streaming.transport (StreamingConfig default is transport:"edit", which
  # disables send_draft). Without transport:auto the consumer streams via
  # edit_message — which our adapter does not consume incrementally — so the
  # turn falls back to feature-006. Rewrite the whole streaming: block
  # deterministically (idempotent; local dev box — other platforms dormant).
  awk '
    /^streaming:[[:space:]]*$/ { print; print "  enabled: true"; print "  transport: auto"; instream=1; next }
    instream && /^[^[:space:]#]/ { instream=0 }
    instream { next }
    { print }
  ' "$CFG" > "$CFG.f007tmp" && mv "$CFG.f007tmp" "$CFG"
  if grep -qE '^streaming:' "$CFG"; then
    echo "streaming: { enabled: true, transport: auto } set"
  else
    printf '\nstreaming:\n  enabled: true\n  transport: auto\n' >> "$CFG"
    echo "streaming: block appended (enabled:true, transport:auto)"
  fi

  say "Restart local gateway"
  hermes gateway restart || hermes gateway start || hermes gateway status \
    || { echo "FAIL: gateway restart"; exit 1; }

  if ! postverify; then
    echo "ROLLBACK: cp ~/.hermes/$(cat "$STATE_DIR/last_backup_local") $CFG ; remove $PLUGIN_DST ; restart"
    exit 1
  fi
  say "DEPLOY OK (local)"
  echo "Next: open the Electron client pointed at http://localhost:8643 / :8644 (no tunnel)."
}
main "$@"
