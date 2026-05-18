# Implementation Plan: Realtime Voice Platform Adapter

**Branch**: `001-realtime-voice-adapter` | **Date**: 2026-05-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-realtime-voice-adapter/spec.md`
**Re-plan note**: Updated after the running Hermes became reachable via
`ssh hermes`. Verification gates VG-1..VG-4 are now **resolved against the live
build** (hermes-agent **v0.13.0**, editable install at
`/home/ubuntu/.hermes/hermes-agent/`), not deferred unknowns.

## Summary

Build a Hermes gateway **platform adapter** giving any connected voice client a
real-time spoken conversation: inbound speech → Hermes-managed STT → Hermes
agent → Hermes-managed TTS → outbound speech, with barge-in. The adapter is a
thin transport + registry layer; STT, the agent loop, TTS, and end-of-utterance
detection are reached **only through `hermes_bridge`** (constitution I). The
bridge now delegates to concrete, verified Hermes v0.13.0 entrypoints.

## Technical Context

**Language/Version**: Python 3.11+ (running Hermes host: Python 3.12.3; aiortc
ok). Adapter code stays 3.11-compatible.
**Primary Dependencies**: `aiortc` (WebRTC/Opus/ICE), `aiohttp` (signaling +
management + control WS), `av`/`ffmpeg` (PCM/Opus + temp-WAV for STT — ffmpeg
already on the Hermes host), plus the **in-process Hermes package**
(`tools.transcription_tools`, `tools.tts_tool`, `tools.voice_mode`,
`gateway.platform_registry`) consumed via `hermes_bridge`, never vendored.
**Storage**: In-memory client/session registry. Config = existing
`~/.hermes/config.yaml` (`satellite:` block added; `stt:`/`tts:` reused
unchanged). Secrets = existing `~/.hermes/.env`. No DB.
**Testing**: `pytest`+`pytest-asyncio`; full suite runs against `FakeTransport`
+ `FakeHermesBridge` (no aiortc/Hermes/hardware needed). A live smoke runs on
the Hermes host where the real package is importable.
**Target Platform**: Linux x86_64 Hermes gateway host, LAN.
**Project Type**: Single backend project — one platform adapter package
registered via `PlatformRegistry` like the built-in adapters.
**Performance Goals**: SC-001 reply ≤1.5 s after end-of-speech; SC-003 barge-in
≤300 ms; SC-005 ≥10 concurrent; SC-006 control plane ≥99%.
**Constraints**: no embedded STT/TTS/agent/endpointing (I); one device-agnostic
contract (II); two connections, no durable control on a data channel (III);
reuse Hermes config/secrets/providers/silence/logs (IV); decisions verified
against the live build (V).
**Scale/Scope**: small LAN fleet, ~10–25 concurrent sessions; transport
security + per-client auth deferred (spec Assumptions).

**Resolved integration surface (Hermes v0.13.0, verified read-only over SSH):**

| Gate | Concrete Hermes entrypoint (verified) | Bridge usage |
|------|----------------------------------------|--------------|
| VG-1 STT | `tools.transcription_tools.transcribe_audio(file_path, model=None) -> dict`; provider+fallback from `_load_stt_config()` (local/groq/openai/mistral/xai); text via `_extract_transcript_text` | write inbound PCM → temp WAV → `transcribe_audio()` → text |
| VG-1 TTS | `tools.tts_tool.text_to_speech_tool(text, output_path=None) -> str(JSON)`; provider/voice from `tts:` config; returns `file_path`/`MEDIA:` | call → parse JSON → read audio file → PCM/Opus |
| VG-2 endpointing | `tools.voice_mode`: authoritative rule `SILENCE_RMS_THRESHOLD=200`, `SILENCE_DURATION_SECONDS=3.0` (+ speech-confirm logic in `AudioRecorder`) | reuse the **rule/constants** applied to decoded WebRTC PCM (the mic-bound `AudioRecorder` itself is not reused — see research D6) |
| VG-3 agent | Platform adapters are transport-only; the **gateway session loop owns the agent** (discord/simplex adapters do not call it directly). Adapter plugs in; gateway routes turns to the agent | adapter delivers user text as a platform message; gateway invokes the agent (constitution IV) |
| VG-4 registration | `gateway.platform_registry.PlatformRegistry.register(PlatformEntry(name, label, adapter_factory: Callable[[PlatformConfig], adapter], check_fn, validate_config?, is_connected?, required_env, source="plugin", plugin_name))`; lifecycle `hermes gateway`; config `hermes gateway setup` | register `PlatformEntry(name="satellite_webrtc", source="plugin")` |

**Remaining narrowed open item (was a full gate, now a sub-item):** the exact
adapter inbound/outbound message methods (connect / receive / send-reply) a
`PlatformRegistry` adapter must implement — to be lifted by reading one full
built-in adapter (`gateway/platforms/discord.py`) on the host. It touches only
the registration shim, not the package core.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Gate | Status |
|---|-----------|------|--------|
| I | Thin Satellite, Gateway-Owned Intelligence (NON-NEGOTIABLE) | Zero STT/TTS/agent/endpointing in-package; all via `hermes_bridge` delegating to verified Hermes entrypoints; no Whisper/Piper import (Hermes internally has them — the adapter never selects them) | ✅ PASS |
| II | Generic Four-Plane Contract | One device-agnostic contract; shared models unchanged; no `device_type` branching | ✅ PASS |
| III | Separate Control and Voice Connections | Always-on WS + per-call WebRTC; no durable control on a data channel | ✅ PASS |
| IV | Reuse Hermes, Don't Rebuild | Registered via `PlatformRegistry`; reuses `~/.hermes/config.yaml` `stt:`/`tts:`/new `satellite:`, `.env`, `transcribe_audio`/`text_to_speech_tool`, voice_mode silence rule, gateway logs | ✅ PASS |
| V | Research-Backed, Constraint-Driven Decisions | VG-1..VG-4 now **verified against the live build v0.13.0** (read-only SSH inspection), not assumed | ✅ PASS (strengthened) |

**Result: PASS (no violations).** Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/001-realtime-voice-adapter/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/{management-api,webrtc-signaling,hermes-bridge}.md
└── tasks.md
```

### Source Code (repository root)

```text
src/hermes_satellite_adapter/
├── __init__.py  models.py  config.py  registry.py  logsink.py
├── hermes_bridge.py    # Protocol + UnboundHermesBridge (existing) AND
│                        #   HermesV013Bridge (NEW): delegates to
│                        #   transcribe_audio / text_to_speech_tool /
│                        #   voice_mode silence rule; agent via gateway session
├── session.py          # state machine + barge-in (unchanged, transport-agnostic)
├── management.py        # /satellite/* + control WS (unchanged)
├── signaling.py         # /webrtc/* + aiortc transport (unchanged)
└── adapter.py           # SatelliteWebRTCAdapter + PlatformEntry registration
                          #   shim (NEW: concrete PlatformRegistry wiring)
tests/{unit,contract,integration}/   # unchanged; FakeHermesBridge still the
                                       #   constitution-I boundary under test
```

**Structure Decision**: Unchanged from the prior plan — the resolved gates only
fill in `hermes_bridge.py` (a new `HermesV013Bridge` alongside the existing
Protocol/`UnboundHermesBridge`) and `adapter.py` (concrete `PlatformEntry`).
The package core, `session.py`, the two-plane split, and the entire test suite
are untouched, exactly as the seam was designed to allow.

## Complexity Tracking

> Not applicable — Constitution Check passed with no violations.
