# Implementation Plan: C++ SDK gRPC Transport

**Branch**: `022-cpp-sdk-grpc-transport` | **Date**: 2026-06-02 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/022-cpp-sdk-grpc-transport/spec.md`

## Summary

Add a gRPC bidirectional-streaming transport to `libaivg-sat` (the C++17 SDK
from feature 020) so a **native device** gets feature 021's reliable audio
plane end-to-end — one `Audio.Stream` (raw 16 kHz PCM up; codec-tagged audio +
transcripts + turn events down), no ICE/DTLS/SCTP to stall. It consumes the
**same** canonical contract the gateway speaks (`proto/aivg/satellite/v1/`), so
the wire cannot drift.

Two things shape the work:

1. **There is no transport seam yet.** `LibpeerTransport` is a concrete class
   held as a direct member of `VoiceSession`, with a WebRTC-specific
   offer/answer interface. Phase 1 therefore **introduces an abstract
   `Transport` interface** at the right altitude (begin/stop, push mic audio,
   remote-audio + event callbacks — *not* SDP), refactors `LibpeerTransport`
   behind it (no behaviour change), and adds `GrpcTransport` as a sibling.
   `VoiceSession` holds a `std::unique_ptr<Transport>`. This generalizes the
   mechanism instead of duplicating `VoiceSession` — the correct altitude.

2. **The tiers are not equal (the binding constraint).** The RPi Zero 2 W /
   POSIX tier ships full gRPC C++ (`grpc++` + protobuf) — this is the MVP
   (US1). The ESP32-S3 / ESP-IDF tier **almost certainly cannot host `grpc++`**
   (it does not build for ESP-IDF; it is server-scale). Per Constitution V the
   ESP32 path must be chosen from *measured* evidence, which requires an
   on-hardware spike — so this feature **scopes ESP32-S3 to stay on WebRTC**
   (US2 = the research spike + decision gate), with a documented nanopb +
   minimal-HTTP/2 path as the candidate to validate before it's committed.

WebRTC stays on both tiers; gRPC is additive and selected by capability
negotiation (aligns with feature 021 / US3). Constitution III — generalized to
be transport-neutral in **v2.1.0** — makes a gRPC voice plane on a native
satellite explicitly constitutional.

## Technical Context

**Language/Version**: C++17 (matches feature 020). Contract bindings generated from `proto/` via `protoc` + `grpc_cpp_plugin`.
**Primary Dependencies**:
- **NEW (RPi/POSIX tier only)**: `grpc++` (gRPC C++ core + C++ API), `protobuf` (runtime), `protoc`+`grpc_cpp_plugin` (build-time codegen).
- Existing, reused: `libpeer` (WebRTC), `opus` (`OpusBridge` — reused for downstream Opus decode), `mbedtls`, `nlohmann/json` (control-plane JSON, unchanged in Phase 1).
- **ESP32-S3 tier**: NO `grpc++` (stays WebRTC this feature). Future candidate: `nanopb` + a minimal HTTP/2 client (research-gated, not adopted here).
**Storage**: N/A (client SDK).
**Testing**: `ctest` pure-logic tests (extend `compile_check`/`test_logic`); a NEW in-process **`FakeTransport`** (enabled by the new seam) to unit-test `VoiceSession` against the gRPC path without hardware; live smoke test (`grpc_audio_smoke`) against a real gRPC gateway. Constitution V on-hardware soak is a release gate, not CI.
**Target Platform**: RPi Zero 2 W-class Linux (POSIX) — **gRPC**; ESP32-S3 (ESP-IDF ≥5.0) — **WebRTC** (gRPC deferred behind a measured spike).
**Project Type**: C++ library / SDK, two-tier (POSIX library + ESP-IDF component). Extends `sdks/cpp/`.
**Performance Goals**: Remove the per-session WebRTC negotiation (~1 s) from end-of-speech→first-audio (SC-003). Upstream raw PCM s16le 16 kHz, 20 ms (640 B) frames — and **no on-device Opus encode on the upstream gRPC path** (a CPU saving vs the WebRTC path).
**Constraints**: ESP32-S3 binary size + PSRAM/heap are the binding constraints that force the tier split (FR-008/Constitution V). `grpc++` MUST be confined to the POSIX tier — an ESP build must not see it (FR-015). Codegen tooling must not be required on a consumer's machine (checked-in or build-fetched generated stubs).
**Scale/Scope**: one `Audio.Stream` per voice session; a handful of devices per gateway. Phase 1 = audio plane (RPi). Phase 2 (later) = management plane over gRPC.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Thin Satellite, Gateway-Owned Intelligence** | ✅ PASS | Pure transport: the SDK streams mic audio and plays replies; no STT/TTS/agent/endpointing added on-device. Device-side wake/VAD only gate the upstream, as today. |
| **II. Generic Four-Plane Contract** | ✅ PASS | The gRPC transport is a new *realization* of the voice plane with identical semantics; the SDK's event surface (`SatEvent`) is unchanged (protobuf `ServerEvent`/`Transcript` map to existing events). No new per-device divergence in the contract. |
| **III. Separate Control and Voice Connections** | ✅ PASS | Explicitly enabled by the **v2.1.0** transport-neutral amendment. Phase 1 keeps the control plane on the WebSocket and swaps only the voice transport to gRPC `Audio.Stream`; the two connections stay separate; durable control never rides the audio stream. |
| **IV. Reuse the Upstream Agent Platform** | ✅ PASS (N/A to client) | The SDK is a client; it doesn't touch the agent platform. It talks to the gateway, which owns STT/TTS/agent. No platform primitive is reimplemented. |
| **V. Research-Backed, Constraint-Driven** | ✅ PASS (with binding obligations) | THE governing principle here. The ESP32-S3 path is **not guessed**: this feature scopes it to WebRTC and defines a measured on-hardware spike (binary size + PSRAM under the full pipeline) as the gate before any ESP32 gRPC is adopted (FR-008/SC-006). The RPi tier must pass the same end-to-end voice loop as WebRTC and a ≥7-day soak (SC-004) before native defaults change. |

**Gate result**: PASS. No violations. The transport-seam refactor is good altitude
(generalize, don't duplicate), not a complexity violation. No Complexity Tracking entries required.

## Project Structure

### Documentation (this feature)

```text
specs/022-cpp-sdk-grpc-transport/
├── plan.md              # This file
├── research.md          # Phase 0 — incl. the ESP32-S3 tier decision
├── data-model.md        # Phase 1 — entities (Transport seam, session, capability set)
├── quickstart.md        # Phase 1 — build + bring-up + validation
├── contracts/           # Phase 1
│   ├── README.md            # consumed wire contract (021's proto) + codegen
│   └── transport-interface.md   # the NEW internal C++ Transport abstraction
└── checklists/
    └── requirements.md  # (from /speckit-specify)
```

### Source Code (repository root)

```text
proto/aivg/satellite/v1/                 # EXISTING (feature 021) — consumed verbatim
└── audio.proto, management.proto

sdks/cpp/
├── CMakeLists.txt                        # EDIT — option(AIVG_SAT_ENABLE_GRPC); protoc codegen; grpc++ link (POSIX only)
├── idf_component.yml                     # unchanged (ESP32 stays WebRTC)
├── cmake/
│   └── GenerateProto.cmake               # NEW — protoc + grpc_cpp_plugin codegen rule (POSIX)
├── src/
│   ├── transport/
│   │   ├── transport.hpp                 # NEW — abstract Transport interface (the seam)
│   │   ├── libpeer_transport.{hpp,cpp}   # EDIT — implement Transport (no behaviour change)
│   │   ├── grpc_transport.{hpp,cpp}      # NEW — Audio.Stream client (POSIX/grpc++)
│   │   └── opus_bridge.{hpp,cpp}         # reused for downstream Opus decode
│   ├── voice_session.{hpp,cpp}           # EDIT — hold unique_ptr<Transport>; PCM-up path for gRPC
│   ├── control_plane.{hpp,cpp}           # EDIT — advertise transport_capabilities; read chosen_transport
│   ├── proto/messages.{hpp,cpp}          # EDIT — register frame gains transport_capabilities
│   ├── grpc/_generated/                  # NEW (checked-in) — audio.pb.{h,cc}, audio.grpc.pb.{h,cc}
│   └── satellite.cpp                      # EDIT — transport selection at session begin
├── include/aivg/sat/                     # public API — additive only (new options, no breaks)
│   └── satellite.hpp                     # EDIT — SatelliteOptions.transport / capabilities (opt-in)
└── tests/
    ├── compile_check.cpp                 # EDIT — gRPC transport instantiates; seam compiles
    ├── test_transport_seam.cpp           # NEW — VoiceSession drives a FakeTransport (no hardware)
    └── grpc_audio_smoke.cpp              # NEW — live: full turn over gRPC vs a real gateway
```

**Structure Decision**: Extend `sdks/cpp/` in place. The pivotal decision is
introducing an **abstract `Transport` seam** (`src/transport/transport.hpp`) so
`GrpcTransport` and the refactored `LibpeerTransport` are siblings and
`VoiceSession` is transport-agnostic — generalizing the mechanism rather than
forking `VoiceSession`. gRPC + protobuf are **POSIX-tier-only** (CMake-gated,
`AIVG_SAT_ENABLE_GRPC`), keeping the ESP-IDF component free of `grpc++`. The
canonical `.proto` is consumed from the existing repo-root `proto/`; C++ stubs
are generated into `src/grpc/_generated/` and checked in (no consumer protoc).

## Complexity Tracking

> No Constitution violations — table intentionally empty. The transport-seam
> refactor is a generalization (correct altitude), not added complexity; the
> ESP32 tier split is forced by a binding hardware constraint (Constitution V),
> not a design preference.
