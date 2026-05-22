---
description: "Task list for libaivg-sat-embedded (C++ WebRTC Satellite SDK)"
---

# Tasks: libaivg-sat-embedded (C++ WebRTC Satellite SDK for PSRAM-class devices)

**Input**: Design documents from `/specs/020-cpp-webrtc-sdk/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: The spec mandates concrete quality gates (FR-021 smoke binary, FR-022 deterministic error-path regress, FR-023 per-tier on-hardware smoke). Those gate tasks are included as deliverables. No speculative/TDD unit tests beyond what the spec requires.

**Organization**: By user story. Story priority reflects the 2026-05-22 "MCU first" clarification — **US2 (ESP32-S3) is the MVP lead**, US1 (RPi Zero 2 W) is the validation tier, US3 is wire parity, US4 (P2) is the hardware-free desktop reference.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- All paths are under `sdks/cpp/` unless noted.

## Path Conventions

New self-contained tree at `sdks/cpp/` (sibling of `sdks/typescript/`). Nothing in `src/aivg_core/` or `sdks/typescript/` changes.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project skeleton + dependency wiring for both tiers

- [X] T001 Create `sdks/cpp/` tree (`include/aivg/sat/`, `src/`, `src/platform/`, `src/transport/`, `src/proto/`, `examples/desktop_smoke/`, `examples/esp32s3_smoke/`, `tests/`) per plan.md
- [X] T002 [P] Root `sdks/cpp/CMakeLists.txt`: C++17, options `AIVG_SAT_BUILD_EXAMPLES` + tier flags (`AIVG_SAT_TIER_POSIX`), `FetchContent` for `libpeer` (MIT) + `nlohmann/json`
- [X] T003 [P] `sdks/cpp/idf_component.yml`: ESP-IDF component manifest declaring `libpeer`, `mbedtls`, `libsrtp`, `opus`, `esp_websocket_client` deps
- [X] T004 [P] `sdks/cpp/.clang-format`, `.clang-tidy`, and `sdks/cpp/.gitignore` (ignore `build/`, IDF `managed_components/`)

**Checkpoint**: Tree builds an empty target; dependencies resolve via FetchContent.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared SDK core — the public API surface plus the host (POSIX) implementation that every user story builds on. The host build here is the inner-loop dev + verification vehicle.

**⚠️ CRITICAL**: No user-story phase can begin until this phase is complete.

- [X] T005 [P] Public header `include/aivg/sat/satellite.hpp`: `Satellite` class, `SatelliteOptions`, `ReconnectPolicy` (per contracts/public-api.md)
- [X] T006 [P] Public header `include/aivg/sat/events.hpp`: `SatEvent` discriminated union — all 17 variants matching `sdks/typescript/src/events.ts`
- [X] T007 [P] Public header `include/aivg/sat/errors.hpp`: `SatError` + `SatErrorCode` enum with the verbatim code strings (research.md R7)
- [X] T008 [P] Public header `include/aivg/sat/audio.hpp`: `AudioInputCallback` / `AudioOutputCallback` (PCM16 mono)
- [X] T009 [P] `src/proto/wire_shapes.hpp`: `SatelliteState`, `SatelliteConfig`, `LogEntry`, `OtaManifest`, `OtaProgress`, `StateChangePayload` mirroring `sdks/typescript/src/proto/` (contract 0.2.0)
- [X] T010 Local FSM (`idle|listening|speaking|error`) + transitions in `src/state_machine.cpp` (data-model.md; note `thinking` is gateway_state, not local)
- [X] T011 `src/platform/ws_client.hpp`: internal `WsClient` interface (control-plane abstraction, Principle III)
- [X] T012 `src/platform/ws_client_posix.cpp`: POSIX `WsClient` over mbedTLS (reuses libpeer's mbedTLS)
- [X] T013 `src/control_plane.cpp`: register, heartbeat, config-push, command, log, OTA passthrough over `WS /satellite/ws` (depends on T011, T012)
- [X] T014 `src/control_plane.cpp` reconnect: exponential backoff + jitter, capped (FR-015) — consumer sees only `gateway_state` transitions
- [X] T015 `src/transport/libpeer_transport.cpp`: libpeer PeerConnection, full ICE gather-then-offer, DTLS-SRTP (FR-012)
- [X] T016 `src/signaling.cpp`: `POST /webrtc/offer`, answer-shape variants, fabricate local session id (FR-011); signaling URL separate from management URL
- [X] T017 `src/transport/opus_bridge.cpp`: Opus encode (mic PCM16 → wire) + decode (wire → output PCM16) bridging the audio callbacks (Principle I compliant — transport codec, not STT/TTS)
- [X] T018 `src/voice_session.cpp`: long-lived session + mute/unmute PTT WITHOUT PeerConnection teardown (FR-010); barge-in handling
- [X] T019 `src/satellite.cpp`: orchestrate `connect/disconnect/beginSession/endSession/mute/unmute`, inspectors, and `SatEvent` dispatch (depends on T010–T018)
- [ ] T020 Host build target in `CMakeLists.txt`: `libaivg_sat` static + shared, plus a minimal host runner used for inner-loop verification (depends on T019)

**Checkpoint**: `libaivg_sat` compiles + links on host; a host turn against a live gateway is possible. User-story phases can begin.

---

## Phase 3: User Story 2 — ESP32-S3 MCU tier (Priority: P1) 🎯 MVP

**Goal**: One full PTT voice turn over WebRTC on an ESP32-S3 board with ≥ 4 MB PSRAM, using the same public API as every other tier.

**Independent Test**: Flash `esp32s3_smoke`; board registers → adopts → completes one mic→STT→agent→TTS→speaker turn within 30 s of first PTT (SC-003).

- [ ] T021 [US2] ESP-IDF component build wiring + Kconfig tier flag (`AIVG_SAT_TIER_ESP32S3`) in `sdks/cpp/CMakeLists.txt` (component mode)
- [ ] T022 [P] [US2] `src/platform/ws_client_espidf.cpp`: `WsClient` impl over `esp_websocket_client`
- [ ] T023 [US2] `examples/esp32s3_smoke/sdkconfig.defaults`: enable PSRAM (`CONFIG_SPIRAM`), place libpeer/Opus/DTLS buffers in PSRAM
- [ ] T024 [US2] `examples/esp32s3_smoke/main/`: Wi-Fi bring-up, I2S mic+speaker driver, PTT button, `aivg::sat::Satellite` wiring
- [ ] T025 [US2] On-hardware smoke run: register→adopt→one PTT turn (SC-003, FR-023)
- [ ] T026 [US2] Combined-load test gate (Wi-Fi + Opus + ICE/DTLS-SRTP running together) on real ESP32-S3 — Principle V viability gate; record PSRAM headroom
- [ ] T027 [US2] Add ESP32-S3 row + PSRAM floor (≥ 4 MB) and excluded-boards note to `README.md` supported-hardware matrix (FR-019, SC-008)

**Checkpoint**: MVP — the ESP32-S3 tier completes a turn and is load-test-proven.

---

## Phase 4: User Story 1 — Raspberry Pi Zero 2 W validation tier (Priority: P1)

**Goal**: One PTT voice turn on a Linux small-board (RPi Zero 2 W class), proving the lower-risk validation path on the same shared core.

**Independent Test**: On a RPi Zero 2 W class board, the CMake build produces the smoke binary and completes one turn within 20 s of release (SC-002).

- [ ] T028 [US1] Verify the CMake build on aarch64 Linux (RPi Zero 2 W class) — cross-compile or on-device
- [ ] T029 [US1] RPi Zero 2 W on-hardware smoke: one PTT turn ≤ 20 s (SC-002, FR-023)
- [ ] T030 [US1] Add RPi Zero 2 W row + build recipe to `README.md` supported-hardware matrix

**Checkpoint**: Both hardware tiers complete a turn through the identical API.

---

## Phase 5: User Story 3 — Wire-protocol parity (Priority: P1)

**Goal**: Prove the C++ SDK is byte-shape indistinguishable from `@aivg/sat-sdk` to the gateway, with no contract bump.

**Independent Test**: Gateway logs from a C++ turn and a TS turn against the same gateway diff to zero at message-type + field-name level (SC-005).

- [ ] T031 [US3] Contract-version envelope read + major-version compat check + warn-not-abort on mismatch (FR-014) in `src/control_plane.cpp`
- [X] T032 [P] [US3] Error-code parity audit: assert the C++ `SatErrorCode` set equals `sdks/typescript/src/errors.ts` in `tests/unit/test_error_parity.cpp`
- [ ] T033 [US3] Parity harness in `tests/parity/`: drive a C++ turn + a TS turn vs the same gateway, diff gateway logs (SC-005)
- [ ] T034 [P] [US3] Mock-gateway fixtures + deterministic error-path regress (`connection_refused`/`signaling_failed`/`ice_gathering_timeout`) in `tests/mock_gateway/` (FR-022)
- [ ] T035 [US3] Confirm `aivg --contract-version` is unchanged (`0.2.0`) after the feature (SC-006)

**Checkpoint**: Wire parity proven; contract version untouched.

---

## Phase 6: User Story 4 — Desktop reference smoke (Priority: P2)

**Goal**: A hardware-free reference sample any contributor can build and run quickly — the everyday regression gate.

**Independent Test**: On a stock Linux/macOS dev machine, the documented build succeeds and the sample completes one turn against a local gateway in ≤ 30 min total including reading the doc (SC-007).

- [ ] T036 [US4] `examples/desktop_smoke/main.cpp`: WAV in → turn → WAV out, CLI args (`--gateway/--signaling/--device-id/--in/--out`)
- [ ] T037 [P] [US4] Optional live mic/speaker via single-header miniaudio, confined to `examples/desktop_smoke/` (FR-007)
- [ ] T038 [US4] Desktop smoke exit code wired as the binding pass/fail for the wire-parity + regression gate (FR-021)
- [ ] T039 [P] [US4] `tests/integration/fetchcontent_consume/`: downstream `FetchContent` one-block consumption check (SC-006)

**Checkpoint**: Hardware-free smoke runs end-to-end and is the CI-able gate.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T040 [P] `sdks/cpp/README.md`: public API, per-tier build steps, one smoke recipe per tier, full supported-hardware matrix (FR-019), TS↔C++ side-by-side parity table (SC-004)
- [ ] T041 [P] Doxygen comment block on every public symbol in `include/aivg/sat/` (FR-020)
- [ ] T042 `cmake --install` + `find_package(aivg_sat)` exporting `aivg::sat` (headers + libs + config)
- [ ] T043 [P] Committed-source size check ≤ 1 MB excluding fetched deps (SC-009)
- [ ] T044 Run `quickstart.md` end-to-end: all three paths (desktop, ESP32-S3, RPi)
- [X] T045 [P] Spec correction: `spec.md` SC-004 "nine" → "the full TS event set" (17); align with research.md finding

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no deps.
- **Foundational (Phase 2)**: depends on Setup. **Blocks all user stories.**
- **US2 (Phase 3, MVP)**: depends on Foundational. The binding v0.1 success gate.
- **US1 (Phase 4)**: depends on Foundational. Independent of US2 (shares the host core; only adds aarch64 verification).
- **US3 (Phase 5)**: depends on Foundational + at least one completed turn path (the host build from Phase 2 suffices; does not require US2/US1 hardware).
- **US4 (Phase 6)**: depends on Foundational. Independent of the hardware tiers.
- **Polish (Phase 7)**: after all targeted stories.

### Within Foundational

- Headers (T005–T009) are parallel.
- `WsClient` (T011) before its impl (T012) before control plane (T013–T014).
- libpeer transport (T015) + signaling (T016) + opus bridge (T017) before voice session (T018).
- Everything before `satellite.cpp` orchestration (T019) and the host target (T020).

### Parallel Opportunities

- T002/T003/T004 (Setup) in parallel.
- T005–T009 (headers) in parallel.
- T022 (ESP-IDF WS shim) parallel with other US2 tasks once T021 lands.
- T032/T034 (parity audit + mock-gateway) parallel.
- Most of Phase 7 ([P]) in parallel.
- With multiple developers, US2 / US1 / US3 / US4 proceed in parallel after Foundational.

---

## Parallel Example: Foundational headers

```bash
Task: "Create include/aivg/sat/satellite.hpp"
Task: "Create include/aivg/sat/events.hpp"
Task: "Create include/aivg/sat/errors.hpp"
Task: "Create include/aivg/sat/audio.hpp"
Task: "Create src/proto/wire_shapes.hpp"
```

---

## Implementation Strategy

### MVP First (User Story 2 — the MCU lead)

1. Phase 1 Setup → 2. Phase 2 Foundational (host core, the blocking bulk) → 3. Phase 3 US2 (ESP32-S3) → **STOP & VALIDATE**: the combined-load test (T026) is the Principle V gate that declares the MVP viable.

> Practical note: the host build from Foundational lets you develop and unit-test the whole core (and even do real gateway turns + parity checks) **before** flashing hardware — de-risking the MCU lead. Build US4's desktop smoke early in practice even though it ships as a P2 deliverable.

### Incremental Delivery

Foundation → US2 (MVP, ESP32-S3) → US1 (RPi validation) → US3 (parity proof) → US4 (desktop reference) → Polish. Each story is independently testable and adds value without breaking prior ones.

---

## Notes

- [P] = different files, no incomplete deps.
- The constitution names `esp_peer` for ESP32S3; this feature uses `libpeer` (MIT) — a recorded Principle V deviation (license; see plan.md Complexity Tracking). T026's combined-load test honors Principle V's "prove before viable" gate.
- No gateway / `aivg_core` / `sdks/typescript` changes anywhere (OOS-002). Contract stays `0.2.0`.
