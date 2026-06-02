---
description: "Task list for feature 022 — C++ SDK gRPC Transport"
---

# Tasks: C++ SDK gRPC Transport

**Input**: Design documents from `/specs/022-cpp-sdk-grpc-transport/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: INCLUDED. The spec's acceptance scenarios, the quickstart, and
Constitution V (proven end-to-end on hardware; constrained tier load-tested)
require them. The new `Transport` seam (research R-1) enables a hardware-free
`FakeTransport` unit test plus a live `grpc_audio_smoke` end-to-end test.

**Organization**: By user story. US1 (RPi gRPC audio plane) is the MVP. US2
(ESP32-S3 tier) is a **measured decision/spike**, not assumed code. US3
(coexistence/negotiation) layers on without breaking existing WebRTC integrations.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 / US2 / US3 (Setup/Foundational/Polish have no story label)

## Path Conventions

C++ SDK at `sdks/cpp/`. Canonical schema consumed from repo-root
`proto/aivg/satellite/v1/` (feature 021, unchanged). Generated C++ stubs are
checked into `sdks/cpp/src/grpc/_generated/`.

---

## Phase 1: Setup (Build & Codegen Scaffolding)

**Purpose**: Land the gRPC build option, codegen, and checked-in stubs.

- [X] T001 Add `option(AIVG_SAT_ENABLE_GRPC "Build the gRPC audio transport" OFF)` to `sdks/cpp/CMakeLists.txt` **inside the POSIX branch only** (after the `if(ESP_PLATFORM) ... return() endif()`), with `find_package(gRPC CONFIG)` + `find_package(Protobuf)`; the ESP-IDF component MUST NOT reference grpc++/protobuf (FR-015).
- [X] T002 [P] Create `sdks/cpp/cmake/GenerateProto.cmake` — a `protoc` + `grpc_cpp_plugin` codegen rule over `proto/aivg/satellite/v1/audio.proto` writing into `sdks/cpp/src/grpc/_generated/` (runs only when `protoc` is found; checked-in stubs otherwise).
- [X] T003 Run the codegen and **commit** `sdks/cpp/src/grpc/_generated/audio.pb.{h,cc}` + `audio.grpc.pb.{h,cc}` (checked-in so a consumer build needs no protoc, R-4).

---

## Phase 2: Foundational — the `Transport` seam (Blocking Prerequisites)

**Purpose**: Introduce the abstract transport interface and route `VoiceSession`
through it. **⚠️ BLOCKS all user stories** — both US1 (gRPC) and US3
(selection) require the seam; the refactor must preserve WebRTC behaviour.

- [X] T004 Create the abstract interface `sdks/cpp/src/transport/transport.hpp` (`class Transport` + `TransportEvent` + `Codec`) exactly per `contracts/transport-interface.md` (audio/lifecycle/event altitude — no SDP methods).
- [X] T005 Refactor `sdks/cpp/src/transport/libpeer_transport.{hpp,cpp}` to implement `Transport` (offer/answer become internals of `begin()`; `send_opus`→`send_mic` encodes via `OpusBridge`; `is_completed()`→`ready()`; peer-failed→`on_event(StreamDropped)`) — **no behaviour change**.
- [X] T006 Change `sdks/cpp/src/voice_session.{hpp,cpp}` to hold `std::unique_ptr<Transport>` (was a concrete `LibpeerTransport` member); route the mic pump through `transport_->send_mic(...)`; map `TransportEvent` → the existing `SatEvent` cases (FR-006).
- [X] T007 Create an in-process `FakeTransport` (records mic PCM, emits scripted remote audio/events) and `sdks/cpp/tests/test_transport_seam.cpp` driving a real `VoiceSession` against it; register as a ctest (R-7).
- [X] T008 Verify a **gRPC-disabled** build is behaviour-identical to feature 020: `sdks/cpp/tests/compile_check.cpp` + existing WebRTC tests stay green (SC-005).

**Checkpoint**: Seam in place; WebRTC unchanged; a transport can be unit-tested without hardware.

---

## Phase 3: User Story 1 — RPi-class native satellite over gRPC (Priority: P1) 🎯 MVP

**Goal**: An RPi Zero 2 W satellite completes a full voice turn over one
`Audio.Stream` (raw PCM up; codec-tagged audio + transcripts + events down), with
no WebRTC negotiation, auto-recovering across restarts.

**Independent Test**: `grpc_audio_smoke` against a real gRPC gateway streams a
short utterance and gets reply audio + transcript/speaking events back; recovery
and latency checks per quickstart §5.

### Tests for User Story 1 ⚠️ (write first)

- [X] T009 [P] [US1] Live end-to-end smoke test `sdks/cpp/tests/grpc_audio_smoke.cpp` — register advertising `["grpc","webrtc"]`, open `Audio.Stream`, stream PCM up, assert reply `AudioChunk` + `Transcript`/`SpeakingStarted` (not a ctest; needs a gateway — mirrors `ws_register_smoke`).

### Implementation for User Story 1

- [X] T010 [US1] Implement `GrpcTransport` lifecycle in `sdks/cpp/src/transport/grpc_transport.{hpp,cpp}`: `begin(session_id)` opens `Audio.Stream` and sends `SessionHeader{session_id, downstream_codec_pref}`; `ready()` = stream open + header sent; `stop()` idempotent.
- [X] T011 [US1] `send_mic` → `ClientFrame.pcm` (`PcmChunk`, raw 16 kHz s16le, 20 ms) — **no on-device Opus encode** on the upstream path (R-3), in `grpc_transport.cpp`.
- [X] T012 [US1] Downstream in `grpc_transport.cpp`: `ServerFrame.audio` → `on_remote_audio(payload, size, codec)` (reuse `OpusBridge` decode for `CODEC_OPUS`, passthrough for PCM); `ServerFrame.event`/`transcript` → `on_event(...)`.
- [X] T013 [US1] Map upstream `ClientEvent` kinds (wake-fired / end-of-utterance / barge-in) onto the stream in `grpc_transport.cpp`.
- [X] T014 [US1] Construct `GrpcTransport` at session begin in `sdks/cpp/src/satellite.cpp` / `voice_session.cpp` when the chosen transport is gRPC; set `VoiceSession.transport = grpc`.
- [X] T015 [US1] Reconnect + drop-surfacing: a dropped `Audio.Stream` → `stop()` + emit the existing `VoiceSessionResult{reason}`; reuse `Satellite::on_reconnected` to rebuild the session on gateway restart (FR-012/FR-013), in `grpc_transport.cpp` / `satellite.cpp`.
- [X] T016 [US1] gRPC channel credentials from `SatelliteOptions`: insecure on trusted LAN (default), `grpc::SslCredentials` for fleet; never silently downgrade a required-auth posture (FR-014), in `grpc_transport.cpp`.

**Checkpoint**: US1 functional — an RPi-class device completes a reliable, auto-recovering voice turn over gRPC. **MVP.** (Soak gate before any default flip — Polish.)

---

## Phase 4: User Story 2 — ESP32-S3 constrained-tier decision (Priority: P2)

**Goal**: A *measured*, recorded decision for the ESP32-S3 tier — either an
on-device gRPC build that provably fits, or a documented WebRTC fallback. No
unmeasured guess (Constitution V).

**Independent Test**: Either a gRPC firmware image with recorded binary-size +
PSRAM/heap-under-full-pipeline numbers that fits and completes an on-device turn,
**or** a measurement-backed decision record keeping ESP32-S3 on WebRTC.

- [X] T017 [US2] Confirm the ESP32-S3 build advertises **only** `["webrtc"]` (no `grpc` capability) and that grpc++/protobuf are never linked into the ESP-IDF component — verify `sdks/cpp/idf_component.yml` + the `if(ESP_PLATFORM)` CMake branch (FR-010/FR-015).
- [X] T018 [US2] Author the spike plan + decision record `specs/022-cpp-sdk-grpc-transport/esp32-grpc-spike.md`: the candidate path (nanopb + minimal HTTP/2 framing), the acceptance bar (fits flash partition + PSRAM/heap headroom under the full pipeline + a completed on-device turn), and how each is measured (FR-008).
- [ ] T019 [US2] Execute the spike (on real ESP32-S3 hardware): produce either a fitting gRPC build with recorded measurements + an on-device turn, **or** a measurement-backed WebRTC-stays decision; record numbers in `esp32-grpc-spike.md` (FR-009/SC-006). *(Hardware task — gated, may run after US1 lands.)*

**Checkpoint**: ESP32-S3 tier has an evidence-backed transport decision.

---

## Phase 5: User Story 3 — Transport coexistence & selection (Priority: P3)

**Goal**: WebRTC and gRPC coexist behind the seam; the device advertises
capabilities and uses the gateway-selected transport; existing WebRTC
integrations are untouched; a developer can pin a transport.

**Independent Test**: a both-transports build is served gRPC; a WebRTC-only build
is served WebRTC; an existing feature-020 integration builds with no source change.

### Tests for User Story 3 ⚠️

- [X] T020 [P] [US3] Extend `sdks/cpp/tests/test_transport_seam.cpp` (or add `tests/test_negotiation.cpp`): advertised `transport_capabilities` reflect build flags; `chosen_transport` selects the right `Transport`; an unsatisfiable pin yields a `SatError`; a WebRTC-only build still selects WebRTC.

### Implementation for User Story 3

- [X] T021 [US3] Add `transport_capabilities` to the register frame in `sdks/cpp/src/proto/messages.{hpp,cpp}` (`build_register`), derived from compiled-in transports (`["grpc","webrtc"]` vs `["webrtc"]`); thread through `sdks/cpp/src/control_plane.cpp` (FR-011/R-5).
- [X] T022 [US3] Read `chosen_transport` from the register reply in `control_plane.{hpp,cpp}` and surface it so `satellite.cpp` selects the matching `Transport` at session begin.
- [X] T023 [US3] Implement a transport pin (`SatelliteOptions.transport` = auto|grpc|webrtc) and an unsatisfiable-pin `SatError` in `satellite.cpp` (FR-011).
- [X] T024 [US3] Add the **additive** public options to `sdks/cpp/include/aivg/sat/satellite.hpp` (`transport`, `grpc_port`, `grpc_tls`) with defaults preserving feature-020 WebRTC behaviour (FR-003/SC-005).
- [X] T025 [US3] Regression: a WebRTC-only build and a pre-021 gateway still complete a turn over WebRTC — assert in `compile_check.cpp` / the negotiation test (FR-011 fallback).

**Checkpoint**: All three stories independently functional; mixed fleet safe; no API break.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T026 [P] Document the gRPC transport in `sdks/cpp/docs/api.md` — `AIVG_SAT_ENABLE_GRPC`, the new options, and `proto/aivg/satellite/v1/` as the consumed contract.
- [X] T027 [P] Add a CHANGELOG / version note for the C++ SDK (gRPC transport; consumes the `0.3.0` contract envelope; RPi-tier-first).
- [X] T028 Run the `quickstart.md` validation (steps 1–4): codegen clean, gRPC build links, seam test green, smoke test against a gateway.
- [X] T029 Add `specs/022-cpp-sdk-grpc-transport/release-gate.md` — the Constitution V gates: RPi ≥7-day soak before flipping native default to gRPC (SC-004); the ESP32-S3 spike acceptance bar.
- [X] T030 [P] Verify SC-005: a `-DAIVG_SAT_ENABLE_GRPC=OFF` build is source-compatible with feature-020 integrations (no public-API break) — note the check in `docs/api.md`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no deps. T003 (commit stubs) depends on T001+T002.
- **Foundational (Phase 2)**: depends on Setup (the gRPC build option + stubs).
  **Blocks all user stories.** T005/T006 depend on T004; T007/T008 depend on T006.
  The seam refactor must keep WebRTC tests green (T008) before US1 begins.
- **US1 (Phase 3)**: depends on Foundational. The gRPC client uses the seam + stubs.
- **US2 (Phase 4)**: depends on Foundational (the capability-advertisement path);
  T019 is a hardware spike that can run after US1 proves the design.
- **US3 (Phase 5)**: depends on Foundational; composes with US1 (selection picks
  the gRPC transport built in US1) but is independently testable via the seam.
- **Polish (Phase 6)**: after the targeted stories.

### User Story Dependencies

- **US1 (P1)**: after Foundational. **MVP.** No dependency on US2/US3.
- **US2 (P2)**: after Foundational. Independent (measurement/decision); the
  WebRTC-only ESP32 path needs only US3's capability advertisement (T021).
- **US3 (P3)**: after Foundational. Selects among transports; testable via
  `FakeTransport` without US1's live gRPC.

### Parallel Opportunities

- Setup: T002 ∥ (T001 then T003).
- Foundational: T004 first; then T005 ∥ start of T006; T007/T008 after T006.
- US1: T009 (test) ∥ T010; then T011/T012/T013 touch `grpc_transport.cpp`
  (sequential), T014–T016 follow.
- Polish: T026 ∥ T027 ∥ T030.

---

## Parallel Example: User Story 1

```bash
# Test + the transport skeleton can start together (different files):
Task: "Live smoke test sdks/cpp/tests/grpc_audio_smoke.cpp"
Task: "Implement GrpcTransport lifecycle in src/transport/grpc_transport.{hpp,cpp}"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 Setup → 2. Phase 2 Foundational (the seam — keep WebRTC green) →
   3. Phase 3 US1.
4. **STOP and VALIDATE**: `grpc_audio_smoke` completes a turn; quickstart §5
   recovery/latency checks on real RPi.
5. Soak (T029 gate) before flipping any native default to gRPC.

### Incremental Delivery

1. Setup + Foundational → seam in place, WebRTC unchanged.
2. US1 → RPi gRPC audio plane → **MVP**, soak.
3. US3 → negotiation/coexistence → safe mixed-fleet rollout.
4. US2 → ESP32-S3 measured decision (gRPC build if it fits, else WebRTC stays).

---

## Notes

- [P] = different files, no incomplete-task dependency.
- The **seam refactor (Phase 2)** is the load-bearing change — it must preserve
  WebRTC behaviour exactly (T008) so existing feature-020 integrations stay green.
- `grpc++`/`protobuf` are **POSIX-tier only** (CMake-gated); the ESP-IDF
  component never links them (FR-015).
- US2's on-hardware spike (T019) and the RPi soak (T029) are Constitution V
  release gates — they can't run in CI; record evidence in the spec dir.
