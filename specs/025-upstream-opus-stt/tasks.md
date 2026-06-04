---
description: "Task list for feature 025 — Opus upstream (mic → STT) voice"
---

# Tasks: Opus upstream (mic → STT) voice

**Input**: Design documents from `/specs/025-upstream-opus-stt/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED — the spec defines a per-story "Independent Test" and the
quickstart enumerates contract + unit + integration + C++ + a live gate. Tests
precede the implementation they cover.

**Organization**: By user story. The wire arm + gateway Opus decode are
foundational. **US1 (MVP)** is the opt-in happy path (device encodes Opus →
gateway decodes → STT) and deliberately needs **no handshake** — a conservative
opt-in flag (default off) never breaks an old gateway. **US3** adds the
register-capability handshake so the device auto-falls-back against a
non-accepting gateway, plus malformed-frame robustness. Mirrors feature 024 on
the upstream direction; reuses PyAV libopus (gateway) + `OpusBridge` (device).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no dependency on incomplete tasks)
- **[Story]**: US1 / US2 / US3 (Setup/Foundational/Polish have no story label)
- Paths are repo-relative from `/Users/yashwant.singh/coderepo/aivg/`

## Path Conventions

Python gateway under `src/aivg_core/` + `src/aivg_cli/`; C++ SDK under `sdks/cpp/`;
canonical contract under `proto/aivg/satellite/v1/`; tests under `tests/` and
`sdks/cpp/tests/`. C++ builds in the `rpi-builder` Docker container (gRPC needs
`grpc++`).

---

## Phase 1: Setup (Contract change + regen)

**Purpose**: Land the additive Opus mic arm in the wire contract and bindings.

- [X] T001 Edit `proto/aivg/satellite/v1/audio.proto`: add `message OpusChunk { bytes payload = 1; uint64 ts_ns = 2; }`, add `OpusChunk opus = 4;` to the `ClientFrame` oneof, and add `repeated Codec upstream_codec_pref = 3;` to `SessionHeader`. Additive only — do not renumber existing fields.
- [X] T002 Regenerate the checked-in **Python** stubs: `bash scripts/gen_proto.sh`; verify `audio_pb2.ClientFrame.DESCRIPTOR.fields_by_name['opus'].number == 4` and `OpusChunk` + `SessionHeader.upstream_codec_pref` exist. Commit `_generated/`.
- [X] T003 Regenerate the checked-in **C++** stubs from the proto (in the `rpi-builder` container or with `protoc`+grpc plugin) into `sdks/cpp/src/grpc/_generated/aivg/satellite/v1/`; verify they compile.

---

## Phase 2: Foundational (Gateway Opus decode engine — blocks US1/US3 gateway side)

**Purpose**: Give the gateway the ability to decode an Opus mic arm to 48 kHz and
feed the existing Session/STT pipeline. All gateway-side stories build on this.

**⚠️ CRITICAL**: No user-story gateway work begins until the decode path exists.

- [X] T004 [P] Write a failing contract test in `tests/contract/test_grpc_contract.py`: assert `ClientFrame` has an `opus` arm (field 4), `OpusChunk` has `payload`/`ts_ns`, and `SessionHeader.upstream_codec_pref` exists.
- [X] T005 Add a stateful `OpusDecoder48k` in `src/aivg_core/transports/grpc/codec.py` (PyAV libopus decoder at 48 kHz s16 mono; `decode(packet) -> bytes`), mirroring the feature-024 `OpusEncoder48k`. Reuse `_audio_fixtures.opus_decode_48k`'s approach.
- [X] T006 Add `GrpcMediaAdapter.push_inbound_opus(payload)` in `src/aivg_core/transports/grpc/media_adapter.py`: decode the Opus packet → 48 kHz PCM → reframe to 20 ms (1920 B) → enqueue on `_in` (the same queue `push_inbound` feeds). Drop on full queue / on decode error (FR-007). Leave the raw-PCM `push_inbound` (16→48) unchanged.
- [X] T007 In `src/aivg_core/transports/grpc/stream_handler.py` `_read_inbound`, dispatch the new arm: `body == "opus"` → `adapter.push_inbound_opus(frame.opus.payload)`; `pcm`/`event`/`session` unchanged.

**Checkpoint**: the gateway can decode an Opus mic arm into the existing 48 kHz → STT pipeline.

---

## Phase 3: User Story 1 - Opus mic audio is transcribed correctly (Priority: P1) 🎯 MVP

**Goal**: A satellite (opted-in) Opus-encodes its 48 kHz mic, the gateway decodes
it, and STT produces a transcript equivalent to the raw-PCM path — at far less
uplink bandwidth. (Opt-in flag, no handshake yet — US3 adds auto-fallback.)

**Independent Test**: Drive a turn where the device sends `opus` mic frames →
the gateway transcribes equivalently to the PCM path; the uploaded bytes are
materially smaller.

### Tests for User Story 1 ⚠️ (write first)

- [X] T008 [P] [US1] Gateway test in `tests/integration/test_grpc_transport_basic.py` (or a new `tests/unit/test_grpc_upstream_opus.py`): feed an `opus` `ClientFrame` (Opus-encode a known 48 kHz tone with PyAV) → assert the decoded audio reaches the Session/STT and the turn completes with a transcript equivalent to the same speech sent as PCM (echo platform `transcribe` confirms received audio length/content).
- [X] T009 [P] [US1] C++ inproc test in `sdks/cpp/tests/grpc_transport_inproc_test.cpp`: with upstream Opus enabled, assert the client sends the `opus` arm (not `pcm`) and `mic_frame_samples() == 960`; the fake server receives `OpusChunk` frames.

### Implementation for User Story 1

- [X] T010 [US1] In `sdks/cpp/src/transport/grpc_transport.{hpp,cpp}`: `send_mic` Opus-encodes the 48 kHz frame via `OpusBridge::encode` (960 samples → one packet) and sends `ClientFrame.opus`; `mic_frame_samples()` returns **960** when upstream Opus is active, else **320**; advertise `upstream_codec_pref=[Opus,PCM_16K]` in the `SessionHeader`. Hold an `OpusBridge` (or reuse the existing one) for encode.
- [X] T011 [US1] In `sdks/cpp/include/aivg/sat/satellite.hpp` add `bool grpc_upstream_opus = false;` (opt-in; conservative default never breaks an old gateway); in `src/satellite.cpp` wire it into `GrpcTransportOptions` (upstream mode = Opus when set). Document the option.

**Checkpoint**: an opted-in satellite's Opus mic uplink is transcribed correctly — the MVP.

---

## Phase 4: User Story 2 - Existing raw-PCM satellites are unaffected (Priority: P1)

**Goal**: The default (flag off) and every pre-feature satellite stream raw 16 kHz
PCM and transcribe exactly as today; the new `opus` dispatch never regresses the
`pcm` path.

**Independent Test**: A device that doesn't enable Opus upstream streams `pcm` and
is transcribed identically to pre-feature behavior.

### Tests for User Story 2 ⚠️ (write first)

- [X] T012 [P] [US2] Gateway test in `tests/unit/test_grpc_media_adapter.py`: the `pcm` `push_inbound` path is byte-for-byte unchanged; a session mixing `opus` and `pcm` frames is handled correctly (each arm dispatched to the right decoder).
- [X] T013 [P] [US2] C++ inproc test: with `grpc_upstream_opus=false` (default), the client sends the `pcm` arm and `mic_frame_samples() == 320` (the existing behavior).

### Implementation for User Story 2

- [X] T014 [US2] Confirm the T006/T007 dispatch leaves the raw-PCM path untouched and the default capture rate is 320; make T012–T013 pass. No new production code expected beyond the dispatch branch — a diff here is a bug in T006/T007/T010.

**Checkpoint**: US1 + US2 — Opus when opted in, unchanged raw PCM otherwise.

---

## Phase 5: User Story 3 - Robust negotiation, fallback & malformed-frame handling (Priority: P2)

**Goal**: A device opted into Opus but talking to a gateway that doesn't accept it
auto-falls-back to raw PCM; a malformed Opus frame is dropped without killing the
session.

**Independent Test**: Point an Opus-opted-in device at a non-accepting gateway →
it streams PCM and transcribes; inject a corrupt Opus packet → the session
survives.

### Tests for User Story 3 ⚠️ (write first)

- [X] T015 [P] [US3] Gateway test: a malformed/undecodable `opus` packet is dropped in `push_inbound_opus` without raising, and the session/turn continues for the rest of the utterance (FR-007).
- [ ] T016 [P] [US3] Negotiation test (C++ + gateway): a device with `grpc_upstream_opus=true` against a gateway that does **not** advertise upstream-Opus acceptance resolves to the PCM path (`mic_frame_samples()==320`, `pcm` arm) and transcribes (SC-004).

### Implementation for User Story 3

- [ ] T017 [US3] Gateway advertises **upstream-Opus acceptance** in the register/adoption reply the device reads before the voice session: add the field to the control-plane WS register reply (and the gRPC `Management` `RegisterReply` in `proto/.../management.proto` + `src/aivg_core/transports/grpc/management_service.py` if that path is used). Additive.
- [ ] T018 [US3] C++ control plane (`sdks/cpp/src/control_plane.*`) parses the acceptance signal; `make_voice_transport`/`GrpcTransport` resolves upstream mode = Opus only when `grpc_upstream_opus && gateway_accepts`, else PCM — and `mic_frame_samples()` reflects the resolved mode (set before the mic pump starts).
- [X] T019 [US3] Harden `push_inbound_opus` (T006) to swallow decode exceptions per-packet (defensive); make T015 pass.

**Checkpoint**: all three stories pass; safe across mixed gateway/device versions.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T020 Bump `CONTRACT_VERSION` `"0.3.0"` → `"0.4.0"` in `src/aivg_cli/cli.py` (additive wire change — new `opus` arm) and update the assertions in `tests/unit/test_cli_help_contract.py`, `tests/unit/test_cli_tagline.py`, `tests/integration/test_install_from_built_wheel.py`.
- [X] T021 [P] Bandwidth test (SC-002) in `tests/unit/test_grpc_upstream_opus.py`: the Opus arms for a fixed utterance total ≥ ~5× fewer bytes than the equivalent raw 16 kHz PCM.
- [X] T022 [P] `CHANGELOG.md` entry: additive `ClientFrame.opus` mic arm; gRPC satellites can send Opus-compressed mic audio decoded gateway-side before STT; contract 0.3.0 → 0.4.0; opt-in, back-compatible.
- [X] T023 [P] Docs: `sdks/cpp/README.md` + `satellite.hpp` document `grpc_upstream_opus` (and the negotiation-dependent mic rate); note ESP32 stays WebRTC.
- [X] T024 Run the full suites green: Python `pytest tests/contract/test_grpc_contract.py tests/unit/test_grpc_media_adapter.py tests/unit/test_grpc_upstream_opus.py tests/integration/test_grpc_transport_basic.py tests/unit/test_cli_help_contract.py tests/unit/test_cli_tagline.py -q`; C++ `ctest` in `rpi-builder`.
- [ ] T025 **Principle V live gate** on `iva` (RPi5 + XVF3800): the C++ satellite with `grpc_upstream_opus=true` captures 48 kHz, Opus-encodes the mic, the gateway decodes → STT transcribes a known phrase **correctly** (equivalent to PCM); measure the uplink-bytes reduction (≥5×); confirm fallback against a non-accepting gateway and that wake/end-of-utterance/barge-in are unaffected. Record the proof.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: proto + regen (Python & C++) — blocks everything (the arm must exist).
- **Foundational (Phase 2)**: gateway Opus decode + dispatch — depends on Setup. **Blocks US1/US3 gateway side.**
- **US1 (Phase 3)**: device encode + opt-in — depends on Setup (C++ stubs) + Foundational (gateway decode). The MVP; no handshake.
- **US2 (Phase 4)**: PCM-unchanged verification — depends on the dispatch (Foundational + US1's `send_mic`).
- **US3 (Phase 5)**: handshake + fallback + malformed — depends on US1 (the Opus path exists) and Foundational (decode). The register-capability work is the heaviest piece.
- **Polish (Phase 6)**: contract bump, bandwidth/docs, suites, live gate — after the stories.

### Within Each User Story

- Tests first (fail), then implementation.
- Gateway decode (Foundational) before device encode (US1) before fallback/handshake (US3).

### Parallel Opportunities

- T002 ∥ T003 (Python vs C++ regen, after T001).
- Per-story `[P]` test-authoring tasks; the implementation tasks are sequential within a story.
- Polish T021/T022/T023 are independent files → parallel.

---

## Parallel Example: Foundational + US1

```bash
# Foundational gateway decode (after Setup):
Task: "T004 contract test for the opus arm"
Task: "T005 OpusDecoder48k in codec.py"   # then T006 push_inbound_opus, T007 dispatch
# US1 tests, then device impl:
Task: "T008 gateway: opus frame -> equivalent transcript"
Task: "T009 C++ inproc: device sends opus arm @ 960"
Task: "T010 C++ send_mic Opus-encode + dynamic mic_frame_samples"
```

---

## Implementation Strategy

### MVP (Setup + Foundational + US1)

1. T001–T003 (contract + regen) → T004–T007 (gateway decode) → T008–T011 (device encode + opt-in).
2. **STOP and VALIDATE**: an opted-in satellite's Opus mic uplink transcribes correctly (the bandwidth win, happy path).

### Incremental Delivery

1. Contract + gateway decode → the gateway can accept Opus mic frames.
2. US1 → device encodes + opt-in → transcribed (MVP).
3. US2 → prove raw PCM unchanged.
4. US3 → handshake auto-fallback + malformed robustness (safe across versions).
5. Polish → contract 0.4.0, bandwidth/docs, live gate on `iva`.

---

## Notes

- **Additive**: proto3 open arm → old↔new interoperate on raw PCM (compat matrix
  in `contracts/upstream-opus-arm.md`).
- **STT-rate refinement**: the gateway feeds STT at 48 kHz already, so the Opus
  path decodes to 48 kHz and joins the existing pipeline — no separate 16 kHz step
  (research Decision 2; flagged to the maintainer).
- **022 R-3 reversal**: this enables on-device Opus encode on the gRPC (RPi) tier;
  ESP32 stays WebRTC. Documented in plan Complexity Tracking.
- The **handshake (T017–T018)** is the heaviest piece (touches the
  register/management plane). The MVP (US1) avoids it via a conservative opt-in
  default; once the handshake lands, the default could flip to on.
- Reuses PyAV libopus (gateway) + `OpusBridge` (device) — no new dependency.
