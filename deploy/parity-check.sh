#!/usr/bin/env bash
# E2 / SC-004 helper: prove the adapter path introduces no STT/TTS quality
# regression vs calling the gateway's configured providers directly.
#
# Runs ON the host, read-mostly (TTS writes a temp file). NOT auto-run — it
# makes real provider calls (possible cost). Operator runs it deliberately
# during the live test and compares against what the Electron client heard.
set -euo pipefail
HOST="${HERMES_SSH:-hermes}"
PHRASE="${1:-the quick brown fox jumps over the lazy dog}"

ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" \
  "cd /home/ubuntu/.hermes/hermes-agent && venv/bin/python - <<PY
import json, tempfile, os
from tools.tts_tool import text_to_speech_tool
from tools.transcription_tools import transcribe_audio, _extract_transcript_text
# Direct provider round-trip (the reference the adapter must match):
raw = text_to_speech_tool('$PHRASE')
meta = json.loads(raw)
path = meta.get('file_path')
print('TTS provider file:', path, 'size:', os.path.getsize(path) if path and os.path.exists(path) else 'n/a')
txt = _extract_transcript_text(transcribe_audio(path))
print('STT round-trip text:', txt)
print('PARITY-REFERENCE: compare this transcript/audio to what the Electron client produced/heard for the same phrase.')
PY"
