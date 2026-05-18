# hermes_satellite_adapter

Hermes gateway **platform adapter** for realtime voice: inbound speech →
Hermes-managed STT → Hermes agent (as the conversational entity) →
Hermes-managed TTS → outbound speech, with barge-in.

Spec & design: `specs/001-realtime-voice-adapter/` (plan.md is the entrypoint;
also referenced from `CLAUDE.md`).

## Constitutional boundaries

- **`hermes_bridge.py` is the only module that touches Hermes intelligence.**
  STT / endpointing / agent / TTS are delegation-only; no Whisper/Piper/engine
  is constructed anywhere (enforced by `tests/unit/test_no_embedded_engines.py`).
- **Two planes, never multiplexed**: `management.py` (control, always-on) vs
  `signaling.py` + `session.py` (per-call WebRTC voice).
- **Reuse, don't rebuild**: config is the existing `~/.hermes/config.yaml`
  `satellite:` block; logs go to the existing `~/.hermes/logs/gateway.log`.

## Layout

| Module | Role |
|--------|------|
| `models.py` | Shared data models (design Appendix B), device-agnostic |
| `config.py` | Loads the `satellite:` block from `~/.hermes/config.yaml` |
| `registry.py` | In-memory client + session registry |
| `logsink.py` | Per-session logs → `gateway.log` + SSE/WS fan-out |
| `hermes_bridge.py` | The ONLY Hermes-intelligence seam (Protocol + gate stub) |
| `session.py` | Conversation state machine + barge-in (transport-agnostic) |
| `management.py` | `/satellite/*` + control WS behaviour |
| `signaling.py` | `/webrtc/*` offer→answer, session wiring |
| `adapter.py` | `SatelliteWebRTCAdapter` + Hermes registration shim (VG-4) |

## Develop & test

```bash
python3.11 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q          # full suite, fake bridge, no aiortc/HW
python -m hermes_satellite_adapter --dev-fake-bridge   # local harness
```

Production wiring of the real Hermes bridge and adapter registration is gated
on running-build verification **VG-1..VG-4** (see `research.md`); only
`hermes_bridge.py` + `adapter.register` change when those close.
