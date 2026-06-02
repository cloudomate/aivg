# Changelog — libaivg-sat (C++ satellite SDK)

## [Unreleased] — Feature 022: gRPC transport

Adds a **gRPC voice transport** alongside the existing WebRTC transport, behind
a new internal `Transport` seam. Consumes the same canonical
`proto/aivg/satellite/v1/` contract as the gateway (feature 021) — no wire
change. The public API is additive; existing WebRTC integrations build and run
unchanged (a `-DAIVG_SAT_ENABLE_GRPC=OFF` build is behaviour-identical to 0.1.0).

### Added

- **gRPC audio plane** (`AIVG_SAT_ENABLE_GRPC`, POSIX/RPi tier): one
  `Audio.Stream` per session — raw 16 kHz PCM up (no on-device Opus encode);
  codec-tagged audio + transcripts + turn events down; insecure-LAN or SSL/mTLS
  credentials; clean drop-surfacing. No ICE/DTLS/SCTP to stall.
- **Abstract `Transport` seam** (`src/transport/transport.hpp`): WebRTC
  (`WebrtcTransport`, composing the untouched `LibpeerTransport`) and gRPC
  (`GrpcTransport`) are siblings; `VoiceSession` is transport-agnostic.
- **Capability negotiation**: the register frame advertises
  `transport_capabilities`; the SDK uses the gateway's `chosen_transport`.
  Additive `SatelliteOptions`: `transport` (Auto/Webrtc/Grpc), `grpc_port`,
  `grpc_tls`. An unsatisfiable pin surfaces a `SatError`.
- Checked-in C++ stubs (`src/grpc/_generated/`) via `cmake/GenerateProto.cmake`
  — no `protoc` needed to consume the SDK.

### Tiers

- **RPi Zero 2 W / POSIX**: gRPC + WebRTC (gRPC is the reliability win — US1).
- **ESP32-S3 (ESP-IDF)**: **stays on WebRTC**; `grpc++`/`protobuf` are never
  linked into the constrained build. On-device gRPC is gated on a measured
  spike — see `specs/022-cpp-sdk-grpc-transport/esp32-grpc-spike.md`.

### Notes

- Consumes the `0.3.0` contract envelope (feature 021 added the `grpc`
  transport). Defaulting native satellites to gRPC is gated on a ≥7-day
  hardware soak (`specs/022-cpp-sdk-grpc-transport/release-gate.md`).

## [0.1.0] — Feature 020: initial C++ SDK

WebRTC-only satellite SDK (libpeer): control plane + per-session WebRTC voice
plane, two tiers (RPi Zero 2 W / POSIX, ESP32-S3 / ESP-IDF).
