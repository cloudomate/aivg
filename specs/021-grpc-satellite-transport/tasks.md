---
description: "Task list for feature 021 — gRPC Satellite Transport"
---

# Tasks: gRPC Satellite Transport

**Input**: Design documents from `/specs/021-grpc-satellite-transport/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: INCLUDED. The spec's acceptance scenarios, quickstart, and
Constitution Principle V (the gRPC native path MUST pass the same end-to-end
voice loop the WebRTC path passes) require contract + integration tests. They
mirror the proven `tests/integration/test_esphome_transport_basic.py` pattern
against the in-repo **echo** test platform — no hardware, no Hermes.

**Organization**: Grouped by user story. US1 (Phase 1 audio plane) is the MVP
and is independently shippable. US2 (Phase 2 management plane) and US3
(coexistence/negotiation) layer on top without breaking US1.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 / US2 / US3 (Setup/Foundational/Polish have no story label)

## Path Conventions

Single project. Canonical schemas at repo-root `proto/`; gateway code under
`src/aivg_core/transports/grpc/`; tests under `tests/{unit,integration,contract}/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Land the contract, dependencies, codegen, and package skeleton.

- [X] T001 Add `grpcio`, `grpcio-tools` (dev), and `protobuf` to `pyproject.toml` dependencies (research R-1: NOT currently present; `grpcio-tools` goes under the `[dev]`/build extra, `grpcio`+`protobuf` are runtime).
- [X] T002 [P] Create canonical schema tree: copy `specs/021-grpc-satellite-transport/contracts/audio.proto` → `proto/aivg/satellite/v1/audio.proto` (single source of truth, FR-001).
- [X] T003 [P] Create `proto/aivg/satellite/v1/management.proto` from `specs/021-grpc-satellite-transport/contracts/management.proto` (Phase 2 schema, design-ahead).
- [X] T004 Create `scripts/gen_proto.sh` invoking `python -m grpc_tools.protoc -I proto --python_out/--grpc_python_out=src/aivg_core/transports/grpc/_generated` for both protos (per contracts/README.md).
- [X] T005 [P] Create package skeleton: `src/aivg_core/transports/grpc/__init__.py` and `src/aivg_core/transports/grpc/_generated/__init__.py` (docstring mirroring `transports/esphome`).
- [X] T006 Run `scripts/gen_proto.sh` and **commit** the generated stubs (`audio_pb2.py`, `audio_pb2_grpc.py`, `management_pb2.py`, `management_pb2_grpc.py`) into `_generated/` (checked-in so `pip install aivg` needs no protoc, research R-2).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Config, models, and the gRPC server lifecycle that every story needs.

**⚠️ CRITICAL**: No user-story work can begin until this phase is complete.

- [X] T007 [P] Add `GrpcTransportConfig` dataclass (`enabled`, `host`, `port=8645`, `tls` ∈ {`insecure`,`mtls`}, `downstream_codec` ∈ {`pcm`,`opus`}, `api_key_file`) to `src/aivg_core/config.py` and add `grpc` field to `TransportsConfig`; parse the `satellite.transports.grpc` block in `from_mapping()` (mirror the `esphome_api` block); extend `validate()` so `grpc.port` differs from management/webrtc ports.
- [X] T008 [P] Extend `src/aivg_core/models.py`: add `transport_capabilities: list[str]` and `transport_pin: Optional[str]` to `ConnectedClient`; document `"grpc"` as a valid value of the existing `transport` field on `ConnectedClient` and `VoiceSession` (no breaking change; defaults preserved).
- [X] T009 Implement the `grpc.aio.Server` lifecycle skeleton in `src/aivg_core/transports/grpc/server.py` — `GrpcAudioTransport(registry, platform, sink, host, port, tls, ui_broadcast)` with `start()`/`stop()` (bind, enable server reflection, register servicers, graceful drain). Side-effect-free `__init__` (mirror `transports/esphome/server.py`).
- [X] T010 Wire the gRPC transport into `src/aivg_core/adapter.py`: construct + `await start()` in `AivgSatelliteAdapter.start()` when `cfg.transports.grpc.enabled`, and `await stop()` in `stop()` (mirror the feature-017 esphome block at lines 115–173); store as `self._grpc_transport`.
- [X] T011 Contract test `tests/contract/test_grpc_contract.py`: assert the checked-in `_generated` stubs import, the `Audio`/`Management` services + messages match `proto/.../*.proto` (regen-and-diff, no drift), and that server reflection is enabled (FR-013/R-2/R-8).

**Checkpoint**: gRPC server binds alongside management (:8643) + WebRTC (:8644); foundation ready.

---

## Phase 3: User Story 1 — Native satellite completes a voice turn over gRPC (Priority: P1) 🎯 MVP

**Goal**: A native satellite streams mic PCM up and plays synthesized reply audio
down over one `Audio.Stream`, reliably, with no WebRTC negotiation — and
auto-recovers across gateway restarts / stream drops.

**Independent Test**: `pytest tests/integration/test_grpc_transport_basic.py` —
a fake client opens `Audio.Stream`, sends `SessionHeader` + PCM + `END_OF_UTTERANCE`,
and receives `SPEAKING_STARTED` + `Transcript` + `AudioChunk` + `SPEAKING_ENDED`
from the echo platform.

### Tests for User Story 1 ⚠️ (write first, ensure they FAIL before implementation)

- [X] T012 [P] [US1] Integration test `tests/integration/test_grpc_transport_basic.py` — full voice turn over gRPC vs the echo platform (mirror `test_esphome_transport_basic.py`).
- [X] T013 [P] [US1] Integration test `tests/integration/test_grpc_transport_reconnect.py` — kill server mid-session, next wake opens a fresh stream and completes a turn with NO renegotiation and NO manual restart (FR-019/FR-020, acceptance scenarios 4/5).
- [X] T014 [P] [US1] Integration test `tests/integration/test_grpc_backpressure.py` — a deliberately slow consumer never makes the gateway buffer unboundedly; `RESOURCE_EXHAUSTED` handled cleanly both ends (FR-021).
- [X] T015 [P] [US1] Unit test `tests/unit/test_grpc_media_adapter.py` — push_inbound/push_eof/drain_outbound, 16 kHz↔48 kHz resample/reframe, bounded-queue behavior.
- [X] T016 [P] [US1] Unit test `tests/unit/test_grpc_codec.py` — downstream codec selection from `downstream_codec_pref` (PCM default, Opus when offered).

### Implementation for User Story 1

- [X] T017 [P] [US1] Implement `GrpcMediaAdapter` (the `MediaTransport` Protocol) in `src/aivg_core/transports/grpc/media_adapter.py`: `receive()`/`send_audio()`/`stop_playback()`/`connection_state`/`close()` plus `push_inbound()`/`push_eof()`/`drain_outbound()`, with 16 kHz↔48 kHz `audioop.ratecv` resample and a **bounded** outbound queue (mirror `transports/esphome/media_adapter.py`; research R-3/R-4).
- [X] T018 [P] [US1] Implement downstream codec selection in `src/aivg_core/transports/grpc/codec.py`: pick from `SessionHeader.downstream_codec_pref` (default `PCM_S16LE_16K`; `OPUS` when client-offered and an encoder is available), emit explicit `AudioChunk.codec` (FR-009/R-4).
- [X] T019 [US1] Implement the per-stream handler in `src/aivg_core/transports/grpc/stream_handler.py`: validate first frame is `SessionHeader`, bind `session_id` to an adopted satellite's open `VoiceSession` (reject missing/invalid header with `FAILED_PRECONDITION`, FR-006), construct `GrpcMediaAdapter` + `Session(model, transport, platform, sink, ui_sink)` and run it (mirror `esphome/connection._start_voice_pipeline`).
- [X] T020 [US1] Implement the `Audio.Stream` servicer in `src/aivg_core/transports/grpc/server.py`, delegating each call to `stream_handler`; set `VoiceSession.transport = "grpc"`.
- [X] T021 [US1] Map upstream `ClientEvent` kinds in `stream_handler.py`: `END_OF_UTTERANCE` → `push_eof()`, `WAKE_FIRED` → explicit session start (FR-012), `BARGE_IN_START` → `Session` barge-in / `stop_playback()`.
- [X] T022 [US1] Emit downstream `ServerFrame`s from the `Session` outputs: `send_audio` → `AudioChunk`, `Session._ui` state → `ServerEvent{SPEAKING_STARTED/ENDED, VAD_DETECTED}`, partial/final text → `Transcript`, all on the same stream (FR-010).
- [X] T023 [US1] Handle stream-drop mid-turn in `stream_handler.py`: end the session cleanly so the next wake re-establishes; emit a terminal signal the client maps to a tone cue (FR-020). (Tone-cue playback itself is client-side, tracked in `aivg-devices`.)
- [X] T024 [US1] Enforce bounded-queue backpressure + clean `RESOURCE_EXHAUSTED` on slow consumer in `media_adapter.py`/`stream_handler.py` (FR-021).
- [X] T025 [US1] Select server credentials from config in `server.py`: `insecure` (trusted-LAN default) vs `mtls` via `grpc.ssl_server_credentials` reusing the device-keystore pattern; never silently downgrade a required-auth posture (FR-022/R-6).
- [X] T026 [US1] Add structured `LogSink` logging for gRPC session lifecycle (stream open/bind/close, codec chosen, drop reason) so a stuck link is diagnosable at one layer (FR-023).

**Checkpoint**: US1 fully functional — a native satellite completes a reliable, auto-recovering voice turn over gRPC. **MVP shippable.**

---

## Phase 4: User Story 2 — Management & control plane over gRPC (Priority: P2)

**Goal**: A native satellite performs its full lifecycle (register, adopt, state,
control, wake/turn) over a gRPC `Management` service, with the `/satellite/ws`
WebSocket disabled — one transport technology for native devices.

**Independent Test**: `pytest tests/integration/test_management_grpc.py` —
register → adopt → report state → receive command, WS disabled.

### Tests for User Story 2 ⚠️

- [X] T027 [P] [US2] Integration test `tests/integration/test_management_grpc.py` — full management lifecycle over gRPC with `/satellite/ws` disabled (acceptance scenarios 1–3).
- [X] T028 [P] [US2] Contract test additions in `tests/contract/test_grpc_contract.py` — `Management` service shape + that its `state_update`/`config_changed`/`command` semantics equal the WebSocket message set (FR-014).

### Implementation for User Story 2

- [X] T029 [US2] Implement `GrpcManagementService` servicer in `src/aivg_core/transports/grpc/management_service.py`: `Register` + bidi `Control` (stream `StateUpdate` ↔ stream `ControlMessage`).
- [X] T030 [US2] Bridge `Control` messages to the existing `ManagementService` (`src/aivg_core/management/service.py`) methods — register/heartbeat/state/config_changed/command — reusing them verbatim so observable semantics are identical (FR-014); no new control semantics.
- [X] T031 [US2] Map `TurnEvent{WAKE_FIRED/END_OF_UTTERANCE}` to precise session-start signalling and the session id that keys `Audio.Stream` (FR-012/FR-006).
- [X] T032 [US2] Mount the `Management` servicer in `server.py` as a SEPARATE long-lived service from `Audio.Stream` (Constitution III intent: durable control never multiplexed into the per-session audio stream); add a config switch to disable `/satellite/ws` for native devices.
- [X] T033 [US2] Ensure `Management` is reflection-introspectable (`grpcurl describe`) for diagnosability (FR-013).

**Checkpoint**: US1 + US2 both work; native satellites can run single-transport.

---

## Phase 5: User Story 3 — Transport coexistence & safe migration (Priority: P3)

**Goal**: Mixed fleet — browsers on WebRTC, legacy natives on WebRTC, new natives
on gRPC — each negotiated from advertised capabilities, no flag-day, with operator pinning.

**Independent Test**: `pytest tests/integration/test_grpc_transport_negotiation.py` —
a client advertising `["grpc","webrtc"]` gets gRPC; a WebRTC-only client gets WebRTC; an esphome client is unaffected.

### Tests for User Story 3 ⚠️

- [X] T034 [P] [US3] Integration test `tests/integration/test_grpc_transport_negotiation.py` — capability negotiation, browser stays WebRTC, legacy esphome/WebRTC natives unaffected, operator pin honored / unsatisfiable pin errors (acceptance scenarios 1–4).

### Implementation for User Story 3

- [X] T035 [US3] Accept `transport_capabilities` in the adoption/registration flow (`src/aivg_core/management/service.py` + `registry.py`) and persist on `ConnectedClient` (FR-015).
- [X] T036 [US3] Implement the gateway transport-selection rule (prefer `grpc` for native, `webrtc` for browser) as a small pure helper (e.g. `src/aivg_core/transports/__init__.py` `select_transport(capabilities, pin, supported)`); set the chosen `transport` at adoption (R-5).
- [X] T037 [US3] Implement `transport_pin` override and a clear, actionable error when a pin cannot be satisfied (FR-017).
- [X] T038 [US3] Add `"grpc"` to `SUPPORTED_TRANSPORTS` in `src/aivg_cli/cli.py` and bump the `contract_version` envelope `0.2.0` → `0.3.0` (additive minor, gated on opt-in advertising the transport) (R-8).
- [X] T039 [US3] Regression guard in `tests/integration/test_grpc_transport_negotiation.py`: confirm browser (WebRTC) + existing esphome + legacy WebRTC native paths are unchanged when gRPC is enabled (FR-016/FR-018).

**Checkpoint**: All three stories independently functional; mixed fleet safe.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T040 [P] Documentation: add the gRPC transport + `transports.grpc` config block to `README.md`/`docs/` and reference `proto/aivg/satellite/v1/` as the shared contract.
- [X] T041 [P] Update `CHANGELOG.md` with the gRPC transport entry (Phase 1 audio plane; note the `0.3.0` contract-envelope bump on opt-in).
- [X] T042 Run the `quickstart.md` validation end-to-end (steps 1–6) against the echo platform.
- [X] T043 Constitution Principle V gate: document the **≥7-day real-hardware soak** (RPi Zero 2 W class) checklist required before defaulting native satellites to `grpc` (SC-004); this cannot run in CI — record as a release gate.
- [X] T044 Governance follow-up: open the recommended **constitution amendment** generalizing Principle III to be transport-neutral (per plan Complexity Tracking + research R-7); link from `plan.md`.
- [~] T045 [P] Optionally advertise the gRPC audio port over mDNS — **DEFERRED**: there is no gateway-side mDNS advertiser today (`mdns_advertise` is only a config-block placeholder; zeroconf is used client-side for ESPHome discovery). Adding one is net-new infrastructure, out of scope for this optional polish task. Revisit if/when a gateway mDNS advertiser lands.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — start immediately. T006 (codegen) depends on T001–T005.
- **Foundational (Phase 2)**: depends on Setup. **Blocks all user stories.** T009/T010 depend on T007/T008; T011 depends on T006.
- **User Stories (Phase 3–5)**: all depend on Foundational. US1 → US2 → US3 in priority order, but each is independently testable; US2/US3 do not modify US1 code paths.
- **Polish (Phase 6)**: depends on the targeted stories being complete.

### User Story Dependencies

- **US1 (P1)**: after Foundational. No dependency on US2/US3. **MVP.**
- **US2 (P2)**: after Foundational. Reuses the same server + session id concept as US1 but is a separate service; independently testable.
- **US3 (P3)**: after Foundational. Negotiation selects among transports; testable without US2. The contract-version bump (T038) is best landed once gRPC is advertisable.

### Within Each User Story

- Tests (T012–T016, T027–T028, T034) written and FAILING before implementation.
- `media_adapter` + `codec` (models-equivalent) before `stream_handler` before the servicer.
- Core turn path before reconnect/backpressure/security hardening.

### Parallel Opportunities

- Setup: T002/T003/T005 in parallel; then T004 → T006.
- Foundational: T007/T008 in parallel; then T009 → T010; T011 after T006.
- US1 tests T012–T016 all [P] together; impl T017/T018 [P] together, then T019–T026 sequential (shared files).
- US2 tests T027/T028 [P]; US3 single test T034.

---

## Parallel Example: User Story 1

```bash
# Tests first (all [P], different files):
Task: "Integration test test_grpc_transport_basic.py"
Task: "Integration test test_grpc_transport_reconnect.py"
Task: "Integration test test_grpc_backpressure.py"
Task: "Unit test test_grpc_media_adapter.py"
Task: "Unit test test_grpc_codec.py"

# Then the two independent building blocks ([P], different files):
Task: "Implement GrpcMediaAdapter in transports/grpc/media_adapter.py"
Task: "Implement codec selection in transports/grpc/codec.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup → 2. Phase 2 Foundational → 3. Phase 3 US1.
4. **STOP and VALIDATE**: `test_grpc_transport_basic` + `_reconnect` + `_backpressure` green; run quickstart steps 1–6.
5. Soak on real hardware (T043) before flipping any native default.

### Incremental Delivery

1. Setup + Foundational → server binds.
2. US1 → reliable gRPC audio plane → **MVP**, soak.
3. US2 → management plane over gRPC → single-transport native.
4. US3 → negotiation/coexistence + contract-version bump → safe fleet rollout.

---

## Notes

- [P] = different files, no incomplete-task dependency.
- The native C++ client (mic capture, tone-cue playback, on-device codec) lives
  in the `aivg-devices` repo and consumes the same `proto/` — out of this task list's scope.
- Phase 1 changes **no** `platforms/` or `webrtc/session.py` code — the
  `MediaTransport`/`Session` seam is reused verbatim.
- Commit after each task or logical group; stop at any checkpoint to validate.
