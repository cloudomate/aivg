# Implementation Plan: libaivg-sat-embedded (C++ WebRTC Satellite SDK for PSRAM-class devices)

**Branch**: `020-cpp-webrtc-sdk` | **Date**: 2026-05-22 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/020-cpp-webrtc-sdk/spec.md`

## Summary

Ship `libaivg-sat`, a C++17 satellite-client SDK whose public API mirrors
`@aivg/sat-sdk` (TypeScript, feature 014) and whose only transport is the
gateway's existing WebRTC voice plane. One SDK source tree, two build
profiles behind one identical API: the **ESP32-S3-class MCU** (ESP-IDF
v5.x, ≥ 4 MB PSRAM — the MVP lead) and the **Raspberry Pi Zero 2 W class
Linux board** (CMake, the supporting/validation tier). Both tiers use the
same MIT-licensed embedded WebRTC library (`libpeer`); Espressif's
`esp-adf-libs`-based stack is excluded because its license is
product-locked. The gateway, wire contract (`0.2.0`), and TypeScript SDK
are untouched — this is satellite-client-side only.

## Technical Context

**Language/Version**: C++17 (matches the 016 draft; the floor that ESP-IDF v5.x and modern Clang/GCC all support)
**Primary Dependencies**: `libpeer` (MIT, WebRTC for ESP32 + Linux/RPi; pulls mbedTLS + libsrtp); `nlohmann/json` (header-only, management-plane JSON); a WebSocket client for the always-on control plane — `esp_websocket_client` (ESP-IDF component) on the MCU tier, a small portable WS client on Linux (see research R4)
**Storage**: N/A (the SDK holds in-memory session state only; the consumer owns any persistence)
**Testing**: CTest + a host-side smoke binary (Linux/macOS) against a live or recorded-mock gateway; on-hardware smokes per tier (ESP-IDF `idf.py` for ESP32-S3, native build for RPi Zero 2 W)
**Target Platform**: ESP32-S3 (Xtensa LX7, FreeRTOS, ESP-IDF v5.x, ≥ 4 MB PSRAM, Wi-Fi) — MVP lead; Raspberry Pi Zero 2 W class (aarch64 Linux) — validation tier; Linux/macOS dev host — reference smoke
**Project Type**: SDK library (C++), consumed via CMake `add_subdirectory`/`FetchContent` (Linux) and as an ESP-IDF component (MCU)
**Performance Goals**: one full PTT voice turn ≤ 15 s (dev host), ≤ 20 s (RPi Zero 2 W), ≤ 30 s (ESP32-S3) from release/first-press (spec SC-001/002/003)
**Constraints**: ≥ 4 MB PSRAM floor; full DTLS-SRTP + Opus + ICE must fit within that budget on the MCU; no wire-contract bump (`aivg --contract-version` stays `0.2.0`); SDK proper links no system audio backend
**Scale/Scope**: one Satellite object = one control-plane WS + ≤ 1 active WebRTC voice session; small SDK (target ≤ 1 MB committed source); 6 lifecycle methods + 9 event types mirroring the TS SDK

## Constitution Check

*GATE: evaluated against AIVG Constitution v2.0.1.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I — Thin Satellite, Gateway-Owned Intelligence | PASS | SDK does no STT/TTS/agent/endpointing. It transports Opus media and control frames only; the consumer supplies raw PCM in/out via callbacks (FR-005/006). Opus encode/decode is transport compression, not ASR/TTS, and is permitted. |
| II — Generic Four-Plane Contract | PASS | SDK realizes control, voice, capture, and playback planes with the same semantics as every other satellite; reuses `SatelliteState`/`SatelliteConfig`/`LogEntry` shapes verbatim from the wire contract (data-model.md). No gateway changes. |
| III — Separate Control and Voice Connections | PASS | Always-on control WS (`WS /satellite/ws`) + per-session WebRTC; the SDK is the offerer with full ICE gather-then-offer; durable traffic stays on the WS, only call-scoped UI events ride the data channel (FR-009/010, matches TS SDK). |
| IV — Reuse the Upstream Agent Platform | PASS | The SDK is a satellite-side client; it never touches `satellite_core`, any `platforms/<name>/` plugin, STT/TTS, or platform config. Platform-agnostic by construction. |
| V — Research-Backed, Constraint-Driven | PASS *(with recorded deviation)* | See deviation below. The WebRTC-library choice and the PSRAM floor are both forced by cited, verified constraints. Principle V's combined-load gate is honored: ESP32-S3 viability is declared only after a full-pipeline (Wi-Fi + Opus + ICE/DTLS-SRTP) load test (a tasks-phase gate). |

**Recorded deviation (Principle V / Hardware & Platform Constraints section).**
The constitution's Hardware section names `esp_peer` (Espressif's
WebRTC) for the ESP32S3 satellite. This plan instead selects `libpeer`
(MIT). The deviation is *driven by* Principle V (research-backed,
validated): `esp_peer` depends on `esp-adf-libs` components licensed
under `LicenseRef-Espressif-Modified-MIT`, which restricts use to
Espressif products and prohibits redistribution for non-Espressif use —
unusable for a redistributable open SDK (verified 2026-05-22; GitHub's
license detector 404s on the repo, and `esp-adf-libs/esp_audio_codec/
LICENSE` states the restriction verbatim). Recorded in Complexity
Tracking below and in the spec's Clarifications section.

**Note on build order.** The constitution's risk-ordered build workflow
is "browser → ESP32 → RPi." This feature's "MCU-first" priority (spec
clarification) inverts that for SDK development, but the spirit is
preserved: the lower-risk Linux tier ships *alongside* the MCU tier as
its validation path, and MCU viability is gated on the combined-load
test, not asserted up front.

## Project Structure

### Documentation (this feature)

```text
specs/020-cpp-webrtc-sdk/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (public C++ API + wire-parity contract)
│   ├── public-api.md
│   └── wire-parity.md
└── checklists/
    └── requirements.md  # from /speckit-specify + /speckit-clarify
```

### Source Code (repository root)

```text
sdks/cpp/                          # NEW — the C++ SDK (sibling of sdks/typescript/)
├── CMakeLists.txt                 # Linux/macOS/RPi build + FetchContent of libpeer
├── README.md                      # public API, build per tier, smoke recipes, supported-hardware matrix
├── idf_component.yml              # ESP-IDF component manifest (MCU tier)
├── include/aivg/sat/              # public headers (the API surface)
│   ├── satellite.hpp              # Satellite class, SatelliteOptions
│   ├── events.hpp                 # SatEvent discriminated union (9 event types)
│   ├── errors.hpp                 # SatError + stable code enum
│   └── audio.hpp                  # AudioInputCallback / AudioOutputCallback
├── src/                           # implementation (shared across both tiers)
│   ├── satellite.cpp              # lifecycle orchestration
│   ├── control_plane.cpp          # always-on WS: register, heartbeat, config, logs, OTA passthrough
│   ├── voice_session.cpp          # WebRTC offer/answer + mute/unmute PTT model
│   ├── signaling.cpp              # POST /webrtc/offer, answer-shape variants
│   ├── transport/                 # libpeer binding (one impl, build-time profiled)
│   └── platform/                  # tier shims: ws_client_posix.cpp / ws_client_espidf.cpp
├── examples/
│   ├── desktop_smoke/             # Linux/macOS reference smoke (WAV in → turn → WAV out)
│   └── esp32s3_smoke/             # ESP-IDF firmware smoke (mic → STT → agent → TTS → speaker)
└── tests/
    ├── unit/                      # error-path + state-machine tests (host)
    └── mock_gateway/              # recorded-mock fixtures for deterministic error regress (FR-022)
```

**Structure Decision**: A new `sdks/cpp/` tree, sibling to the existing
`sdks/typescript/`. The SDK is a self-contained library; nothing in
`src/aivg_core/` or `sdks/typescript/` changes. The single `src/` is
shared by both tiers; the only tier-specific code is the WebSocket-client
shim under `src/platform/` and build wiring (CMake vs ESP-IDF component),
satisfying FR-004a (one API, build-time-selected profile).

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| WebRTC library `libpeer` instead of constitution-named `esp_peer` | A redistributable open SDK cannot depend on `esp-adf-libs` (product-locked `LicenseRef-Espressif-Modified-MIT`, redistribution for non-Espressif use prohibited). `libpeer` is MIT and covers both ESP32 and Linux/RPi. | `esp_peer`/Espressif WebRTC rejected: license forbids the redistribution this SDK requires. A from-scratch WebRTC stack rejected: enormous scope, fails the "small SDK / ≤ 1 MB" and 5-minute-build goals. |
| Two build systems (CMake + ESP-IDF component) | The two runtimes have incompatible native build tooling; ESP-IDF mandates its own CMake-based component build. | A single CMake invocation cannot produce an ESP32-S3 firmware image; forcing one would reimplement the IDF toolchain. The public API stays identical, so this is build-wiring duplication only, not API divergence. |
