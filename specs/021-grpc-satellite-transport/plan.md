# Implementation Plan: gRPC Satellite Transport

**Branch**: `021-grpc-satellite-transport` | **Date**: 2026-06-02 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/021-grpc-satellite-transport/spec.md`

## Summary

Add a gRPC bidirectional-streaming transport for **native** AIVG satellites,
delivered as an additive sibling under `aivg_core.transports.grpc/` — exactly
the pattern feature 017 used for `transports.esphome/`. Phase 1 moves the
real-time **audio plane** of a voice turn off WebRTC onto a single
`Audio.Stream` gRPC call (mic PCM up, synthesized audio + transcripts + turn
events down). Phase 2 moves the **management/control plane** (registration,
state, adoption, control, wake/turn events) onto a gRPC `Management` service so
native satellites need only one connection technology.

The transport reuses the existing seams verbatim: each gRPC voice stream
constructs a `MediaTransport` adapter (5-method Protocol in
`webrtc/session.py`) and drives the canonical `Session` state machine, which
reaches STT / agent / TTS / endpointing only through the `AgentPlatform`
plugin. No `platforms/` or `webrtc/session.py` change is required for Phase 1.
WebRTC stays for browser satellites; legacy WebRTC natives keep working;
transport is chosen by capability negotiation in the existing adoption flow.

## Technical Context

**Language/Version**: Python 3.11 (gateway/server side, this repo). Canonical
`.proto` is language-neutral; the native client is C++17 (lives in the
companion `aivg-devices` repo, out of this repo's tree).
**Primary Dependencies**:
- **NEW**: `grpcio` (async server via `grpc.aio`), `grpcio-tools` (codegen,
  dev/build only), `protobuf` (runtime). NOTE: contrary to the proposal,
  `grpcio` is **not** currently in the dep tree — `aioesphomeapi` pulls
  `protobuf` but not gRPC. This is a genuine new runtime dependency for the
  gateway (acceptable: the gateway runs in the Hermes venv, not on-device).
- Existing: `aiohttp` (management WS + REST, unchanged in Phase 1), `aioesphomeapi`.
**Storage**: N/A (transport layer; registry stays in-memory + existing persistence).
**Testing**: `pytest` + `pytest-asyncio`, mirroring `tests/integration/test_esphome_transport_basic.py` against the in-repo **echo** test platform (no Hermes, no hardware).
**Target Platform**: Linux gateway (Hermes host). Native satellites (RPi Zero 2 W class, ESP32-S3 class) are the clients — client impl tracked in `aivg-devices`.
**Project Type**: Single project — Python library/adapter loaded by an agent-platform gateway (Constitution IV). No frontend/mobile split.
**Performance Goals**: Remove the per-session WebRTC negotiation overhead (~1 s) from the end-of-speech→first-audio path; first reply audio begins within a small fraction of a second of the gateway producing it (SC-003). Upstream PCM 16 kHz int16 LE, 20 ms frames (640 B) — fits one TCP segment.
**Constraints**: Trusted-LAN default may run `insecure_channel`; fleet uses mTLS (FR-022). Backpressure via HTTP/2 flow control must not desync audio (FR-021). Stuck-link cause must be diagnosable at one layer (FR-023).
**Scale/Scope**: One gRPC stream per voice session; a handful of native satellites per gateway (`device_limit` default 10). Phase 1 = audio; Phase 2 = management/control.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Thin Satellite, Gateway-Owned Intelligence** | ✅ PASS | The gRPC transport is pure transport: inbound audio is routed through `Session` → `AgentPlatform` (`transcribe`/`agent_step`/`synthesize`/`endpoint`). No STT/TTS/agent/endpointing is added on either side. Device-side wake/VAD only *gates* upstream, as today. |
| **II. Generic Four-Plane Contract** | ✅ PASS | gRPC realizes the same four logical planes (control, voice, capture/endpoint, playback) with identical semantics. The gateway registry/management/dashboard MUST NOT branch on transport — selection is data (`transport` field), handled at the edge (like `esphome_api`). `SatelliteState`/`SatelliteConfig`/`LogEntry` used unchanged. |
| **III. Separate Control and Voice Connections** | ⚠️ **DEVIATION (recorded)** | Principle III names the voice plane as **WebRTC** and durable control as the **`/satellite/ws` WebSocket**. This feature replaces the voice plane with gRPC (Phase 1) and the control plane with gRPC (Phase 2) **for native clients only**. The *intent* of III — control availability decoupled from call state, durable traffic off the call-scoped channel — is **preserved**: Phase 1 keeps the management WebSocket as the always-on control plane and only swaps the voice transport; Phase 2 keeps control and voice as **separate gRPC services/streams** (`Management` long-lived, `Audio.Stream` per-session), never multiplexing durable control into the per-session audio stream. See Complexity Tracking + research R-7. A constitution amendment to generalize III ("a control connection and a per-session voice connection", transport-neutral) is recommended as a follow-up, mirroring how IV was generalized in v2.0.0 — drafted in [followup-principle-iii-amendment.md](./followup-principle-iii-amendment.md). |
| **IV. Reuse the Upstream Agent Platform** | ✅ PASS | Transport reaches intelligence only via the `AgentPlatform` Protocol through the shared `Session`. No new config/secret store: a `transports.grpc` block joins the existing `satellite:` config (parsed by the existing loader); mTLS material reuses the device keystore pattern. Adding gRPC requires no change in `platforms/`. |
| **V. Research-Backed, Constraint-Driven** | ✅ PASS (with obligation) | Decisions (codec, framing, sample rate, security) are justified in research.md. Per V, the gRPC native path MUST pass the same end-to-end voice loop the WebRTC path passes, and be soak-tested on real hardware (SC-004) before it is declared supported — captured as a release gate in [release-gate.md](./release-gate.md). |

**Gate result**: PASS with one **recorded deviation** (Principle III), justified
in Complexity Tracking. No unjustified violations.

## Project Structure

### Documentation (this feature)

```text
specs/021-grpc-satellite-transport/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── audio.proto      # Phase 1 canonical audio-plane schema
│   ├── management.proto # Phase 2 control-plane schema (design-ahead)
│   └── README.md        # contract notes, versioning, codegen
└── checklists/
    └── requirements.md  # (from /speckit-specify)
```

### Source Code (repository root)

```text
proto/                                   # NEW — canonical, language-neutral schemas
└── aivg/satellite/v1/
    ├── audio.proto                      # Phase 1 (single source of truth; aivg-devices vendors this)
    └── management.proto                 # Phase 2

src/aivg_core/transports/grpc/           # NEW — mirrors transports/esphome/
├── __init__.py                          # exports GrpcAudioTransport (+ GrpcManagementService in Phase 2)
├── _generated/                          # checked-in codegen (audio_pb2.py, audio_pb2_grpc.py, …)
│   └── __init__.py
├── server.py                            # grpc.aio.Server lifecycle (≈ esphome/server.py)
├── stream_handler.py                    # per-Audio.Stream lifecycle (≈ esphome/connection.py)
├── media_adapter.py                     # MediaTransport impl: PCM in/out + resample (≈ esphome/media_adapter.py)
├── codec.py                             # downstream Opus/PCM encode selection (FR-009)
└── management_service.py                # Phase 2 — Management gRPC servicer

src/aivg_core/
├── adapter.py                           # EDIT — start/stop the gRPC transport (mirror esphome block)
├── config.py                            # EDIT — add GrpcTransportConfig to TransportsConfig
└── models.py                            # EDIT — transport capability set; "grpc" as a transport value

src/aivg_cli/cli.py                      # EDIT — SUPPORTED_TRANSPORTS += "grpc"; contract-version bump

scripts/
└── gen_proto.sh                         # NEW — protoc invocation (regenerates _generated/)

tests/
├── unit/
│   ├── test_grpc_media_adapter.py       # NEW — resample/reframe, queue/backpressure
│   └── test_grpc_codec.py               # NEW — codec selection
├── integration/
│   ├── test_grpc_transport_basic.py     # NEW — full voice turn over gRPC vs echo platform
│   ├── test_grpc_transport_reconnect.py # NEW — gateway restart / stream drop recovery (FR-019/20)
│   ├── test_grpc_backpressure.py        # NEW — slow consumer (FR-021)
│   ├── test_grpc_transport_negotiation.py # NEW — capability negotiation/coexistence (US3)
│   └── test_management_grpc.py          # NEW (Phase 2) — register/adopt/state/control over gRPC
└── contract/
    └── test_grpc_contract.py            # NEW — proto/generated parity, contract-version envelope
```

**Structure Decision**: Single project. The canonical `.proto` lives at the
repo-root `proto/` tree (language-neutral, vendored by `aivg-devices` for the
C++ client) and is the one source of truth (FR-001). Python bindings are
codegen'd into `transports/grpc/_generated/` and **checked in**, so `pip
install aivg` needs no `protoc`. The transport follows the esphome sibling
pattern: a `server.py` listener, a per-stream handler, and a `media_adapter.py`
implementing `MediaTransport` — keeping `platforms/` and `webrtc/session.py`
untouched in Phase 1.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| **Principle III deviation**: voice plane moves from WebRTC→gRPC (Phase 1); control plane moves from `/satellite/ws` WebSocket→gRPC (Phase 2), for native clients. | WebRTC's ICE/DTLS/SCTP stack is the documented root cause of the "stuck connecting" field failures (upstream bug 5); every layer is a stall point on a LAN where NAT traversal and browser-grade E2E encryption buy nothing. gRPC bidi streaming is the primitive Google's Assistant SDK uses for exactly this. | (a) *Keep WebRTC, harden it* — already tried (boot-order guards, watchdog, manual restarts); papers over the hole, failure recurs. (b) *Plain WebSocket audio plane* — would satisfy III's letter but loses schema discipline, native bidi-stream typing, deadlines/cancellation, and gRPC tooling; the spec/proposal explicitly chose gRPC over WS for a multi-year production transport. (c) *Defer Phase 2* — allowed; Phase 1 alone keeps III's control-plane WS intact. The deviation is scoped to native clients; browsers stay fully on III's WebRTC + WS. III's *intent* (control decoupled from call state; durable traffic off the per-session channel) is preserved by keeping `Management` and `Audio.Stream` as separate gRPC surfaces. |
| **New runtime dependency `grpcio`** | No gRPC transport is possible without it; the proposal's assumption that it was already transitively present is incorrect. | Re-using `aioesphomeapi`'s raw varint-framed-protobuf-over-TCP (no gRPC) would avoid the dep but throws away the entire rationale (HTTP/2 multiplexing, reflection, `grpcurl`, retry/deadline semantics) — i.e., it would be "plain framed sockets," not the chosen transport. |
