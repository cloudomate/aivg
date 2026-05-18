# Implementation Plan: Realtime Voice Platform Adapter

**Branch**: `001-realtime-voice-adapter` | **Date**: 2026-05-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-realtime-voice-adapter/spec.md`

## Summary

Build a Hermes gateway **platform adapter** that gives any connected voice
client a real-time spoken conversation: inbound speech → Hermes-managed STT →
Hermes agent (as the conversational entity) → Hermes-managed TTS → outbound
speech, with barge-in. The adapter is a thin transport + registry layer: it
owns a per-client always-on control WebSocket and a per-call WebRTC voice
session, and reaches STT, the agent loop, TTS, and end-of-utterance detection
**only through Hermes's existing provider interfaces** — it instantiates none
of them. Approach is grounded in `docs/generic-voice-satellite-design.md` (§8,
Appendix A, Appendix E) and the project constitution.

## Technical Context

**Language/Version**: Python 3.11+ (matches Hermes gateway runtime and aiortc)
**Primary Dependencies**: `aiortc` (WebRTC: PC, Opus, ICE/DTLS-SRTP),
`aiohttp` (HTTP signaling + management plane + control WebSocket), `av`/
`ffmpeg` (PCM/Opus resample, already available in Hermes), Hermes gateway
adapter base + STT/TTS/agent/endpointing provider interfaces (consumed, not
vendored)
**Storage**: In-memory device + session registry (process-lifetime).
Configuration in existing `~/.hermes/config.yaml` (`satellite:` block);
secrets in existing `~/.hermes/.env`. No database.
**Testing**: `pytest` + `pytest-asyncio`; aiortc loopback PC for the voice
path; a fake Hermes provider double for STT/TTS/agent/endpointing
**Target Platform**: Linux server (Hermes gateway host), LAN deployment
**Project Type**: Single backend project — one platform adapter package
registered inside the existing Hermes gateway (analogous to telegram/discord
adapters)
**Performance Goals**: spoken reply begins ≤1.5 s after end-of-speech
(SC-001); barge-in playback stop ≤300 ms (SC-003); ≥10 concurrent sessions
within 1.5× latency (SC-005); control plane ≥99% available (SC-006)
**Constraints**: adapter adds no embedded STT/TTS/agent/endpointing
(constitution I); one device-agnostic contract, no `device_type` protocol
branching (II); two separate connections, no durable control over a data
channel (III); reuse Hermes config/secrets/providers/silence/logs (IV);
full ICE gather-then-offer, satellite is offerer / adapter is answerer;
Opus 48 kHz mono
**Scale/Scope**: small LAN fleet, ~10–25 concurrent voice sessions; transport
security + per-client auth explicitly deferred (out of scope, see spec
Assumptions)

**Open integration unknowns (resolved in Phase 0 research.md, with
verification gates):** the exact running-Hermes build surface — provider
interface signatures for STT/TTS, the agent invocation entrypoint, the
end-of-utterance/silence API, and the adapter registration + CLI surface
(`hermes gateway` / `hermes gateway setup`). The design doc itself flags these
as open (§8.3). They are resolved as grounded decisions plus a mandatory
"verify against the running build" gate, not left as blockers.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Gate | Status |
|---|-----------|------|--------|
| I | Thin Satellite, Gateway-Owned Intelligence (NON-NEGOTIABLE) | Adapter contains zero STT/TTS/agent/endpointing logic; all reached via Hermes provider interfaces; no Whisper/Piper import; device VAD only gates upstream, Hermes owns turn-end | ✅ PASS — `hermes_bridge` is wrappers only; FR-002/003/004/005 enforce |
| II | Generic Four-Plane Contract | One device-agnostic contract; `SatelliteState`/`SatelliteConfig`/`LogEntry` used unchanged; no `device_type` protocol branching in registry/dashboard | ✅ PASS — single Session/contract; models per Appendix B |
| III | Separate Control and Voice Connections | Always-on control WS + per-call WebRTC; durable control never on a data channel; satellite offerer / adapter answerer; full ICE gather-then-offer | ✅ PASS — `management` (WS+REST) and `signaling`/`session` are distinct planes |
| IV | Reuse Hermes, Don't Rebuild | Registered as a platform adapter; reuses config.yaml loader, .env, provider abstractions, server-side silence algo, gateway.log; no new config/secret store | ✅ PASS — `satellite:` block in existing config; logs to gateway.log |
| V | Research-Backed, Constraint-Driven Decisions | Hardware/integration decisions cite binding constraints; open Hermes-surface items carry a verify-before-rely gate; load test before declaring viable | ✅ PASS — research.md records decisions + verification gates |

**Result: PASS (no violations).** Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/001-realtime-voice-adapter/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── management-api.md     # /satellite/* REST + WS /satellite/ws
│   ├── webrtc-signaling.md   # /webrtc/offer|candidate|status
│   └── hermes-bridge.md      # internal contract to Hermes provider interfaces
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
src/hermes_satellite_adapter/
├── __init__.py
├── adapter.py          # SatelliteWebRTCAdapter: registers like telegram/discord;
│                       #   starts the two aiohttp sites; owns lifecycle
├── config.py           # loads/validates the `satellite:` block from
│                       #   ~/.hermes/config.yaml; default_config push
├── models.py           # SatelliteState / SatelliteConfig / LogEntry (Appendix B),
│                       #   echo_strategy enum — used unchanged for all devices
├── registry.py         # in-memory ConnectedClient + VoiceSession registry
├── management.py       # aiohttp :8643 — /satellite/* REST + WS /satellite/ws
│                       #   (control plane: register/heartbeat/config/cmd/logs/OTA)
├── signaling.py        # aiohttp :8644 — /webrtc/offer|candidate|status
├── session.py          # Session: aiortc RTCPeerConnection (answerer),
│                       #   inbound Opus→PCM, outbound PCM→Opus, barge-in,
│                       #   one-turn-at-a-time state machine
└── hermes_bridge.py    # THIN wrappers ONLY: stt_transcribe / detect_endpoint /
                        #   agent_turn / tts_synthesize delegating to Hermes's
                        #   provider interfaces — NO engine instantiation

tests/
├── contract/           # management API + signaling schema conformance
├── integration/        # loopback aiortc PC → fake Hermes bridge → audio back;
│                        #   barge-in; reconnect; provider-fallback; 10x concurrency
└── unit/               # registry, config loader, session state machine, models
```

**Structure Decision**: Single backend project. The adapter is one installable
Python package (`src/hermes_satellite_adapter/`) that the existing Hermes
gateway loads as a platform adapter — it does not run as a standalone daemon
(constitution IV). The two aiohttp sites (`:8643` management, `:8644` WebRTC
signaling) are the only externally exposed surfaces; everything STT/TTS/agent/
endpointing crosses the `hermes_bridge` boundary into Hermes (constitution I).
The package boundary makes the "thin adapter" rule structurally enforceable:
`hermes_bridge.py` is the only module permitted to touch Hermes intelligence,
and it contains delegation only.

## Complexity Tracking

> Not applicable — Constitution Check passed with no violations.
