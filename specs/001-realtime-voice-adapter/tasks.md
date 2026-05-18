---
description: "Task list for Realtime Voice Platform Adapter"
---

# Tasks: Realtime Voice Platform Adapter

**Input**: Design documents from `/specs/001-realtime-voice-adapter/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Test tasks ARE included — the feature explicitly requires a pytest
suite (research.md D12, quickstart.md) so the whole loop can be validated
against a fake Hermes bridge with no live Hermes build or hardware.

**Organization**: Grouped by user story (US1 P1 · US2 P2 · US3 P2 · US4 P3)
for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no incomplete dependencies)
- **[Story]**: US1/US2/US3/US4; Setup/Foundational/Polish have no story label
- Paths follow plan.md: package `src/hermes_satellite_adapter/`, tests `tests/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and structure

- [ ] T001 Create project structure per plan.md: `src/hermes_satellite_adapter/__init__.py` and `tests/{contract,integration,unit}/` package dirs
- [ ] T002 Create `pyproject.toml` declaring Python 3.11+ and deps (`aiortc`, `aiohttp`, `av`, `pytest`, `pytest-asyncio`); `requirements-dev.txt`
- [ ] T003 [P] Configure linting/formatting (`ruff` + `black`) and `pytest.ini`/`pyproject` `[tool.pytest.ini_options]` with `asyncio_mode=auto`
- [ ] T004 [P] Add `.gitignore` entries for `__pycache__/`, `.pytest_cache/`, build artifacts

**Checkpoint**: Project skeleton builds and `pytest` runs (0 tests)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure required by ALL user stories

**⚠️ CRITICAL**: No user story work begins until this phase completes

- [ ] T005 [P] Implement shared data models in `src/hermes_satellite_adapter/models.py` per data-model.md: `ConnectedClient`, `VoiceSession`, `ConversationTurn`, `SatelliteConfig`, `LogEntry`, and the `echo_strategy` enum — used unchanged for all device types (constitution II)
- [ ] T006 [P] Implement `src/hermes_satellite_adapter/config.py`: load/validate the `satellite:` block from `~/.hermes/config.yaml` (ports 8643/8644, heartbeat_interval, mdns_advertise, default_config); reuse `~/.hermes/.env`; no new config/secret store (constitution IV)
- [ ] T007 Implement `src/hermes_satellite_adapter/registry.py`: in-memory `ConnectedClient` + `VoiceSession` registry (upsert, status transitions, one active session per client) — depends on T005
- [ ] T008 [P] Define the `HermesBridge` Protocol in `src/hermes_satellite_adapter/hermes_bridge.py` per contracts/hermes-bridge.md (`stt_transcribe`, `detect_endpoint`, `agent_turn`, `tts_synthesize`) — delegation-only seam, NO engine instantiation (constitution I)
- [ ] T009 [P] Implement `FakeHermesBridge` in `tests/conftest.py` (or `tests/fakes.py`): deterministic transcripts, configurable latency, injectable provider-failure, controllable endpoint signal
- [ ] T010 Implement adapter shell `src/hermes_satellite_adapter/adapter.py`: `SatelliteWebRTCAdapter` that starts the two aiohttp sites (`:8643` management, `:8644` signaling) and owns lifecycle; registration shim is a stub behind VG-4 — depends on T006, T007
- [ ] T011 [P] Add dev entrypoint `python -m hermes_satellite_adapter --dev-fake-bridge` wiring the FakeHermesBridge for local/test runs (not the production path) — depends on T010
- [ ] T012 [P] Constitution-I guard: unit test in `tests/unit/test_no_embedded_engines.py` that fails if `whisper`/`piper`/STT/TTS engine symbols are imported anywhere outside `hermes_bridge.py`
- [ ] T013 [P] Logging infra in `src/hermes_satellite_adapter/models.py`/helper: `LogEntry` sink that writes to Hermes's existing `~/.hermes/logs/gateway.log` stream, attributable per `device_id` (constitution IV) — depends on T005

**Checkpoint**: Foundation ready — user stories can begin

---

## Phase 3: User Story 1 - Real-time spoken conversation (Priority: P1) 🎯 MVP

**Goal**: speech in → Hermes STT → Hermes agent → Hermes TTS → speech out,
within the SC-001 latency budget, over a loopback WebRTC session.

**Independent Test**: Loopback client registers, opens a WebRTC session
(full-gather offer → answer), streams a scripted utterance, hears a
FakeHermesBridge-generated spoken reply; reply audio begins ≤1.5 s after
end-of-speech.

### Tests for User Story 1

- [ ] T014 [P] [US1] Contract test `tests/contract/test_register.py`: `POST /satellite/register` upserts client → `online`, returns `{session_token, management_server_url, default_config}` (contracts/management-api.md)
- [ ] T015 [P] [US1] Contract test `tests/contract/test_webrtc_offer.py`: full-gather `POST /webrtc/offer` returns a valid answer, one audio m-line, no video, Opus 48 kHz mono, no SDP munging (contracts/webrtc-signaling.md)
- [ ] T016 [P] [US1] Integration test `tests/integration/test_p1_conversation.py`: end-to-end loopback loop asserting a spoken reply and SC-001 (≤1.5 s) latency

### Implementation for User Story 1

- [ ] T017 [US1] Implement management `POST /satellite/register` + `WS /satellite/ws` register/heartbeat handlers in `src/hermes_satellite_adapter/management.py` (always-on control plane, separate from voice — constitution III) — depends on T007, T010
- [ ] T018 [US1] Implement signaling `POST /webrtc/offer` (+ `/webrtc/candidate` fallback, `GET /webrtc/status/{id}`) in `src/hermes_satellite_adapter/signaling.py`: aiortc answerer, client is offerer, full-gather then set remote desc; creates a `VoiceSession` bound to the client — depends on T007, T010
- [ ] T019 [US1] Implement `src/hermes_satellite_adapter/session.py` state machine `idle→listening→thinking→speaking→listening` with at-most-one in-flight turn (FR-012) — depends on T005, T018
- [ ] T020 [US1] Session inbound path: aiortc Opus→PCM frames → `bridge.detect_endpoint` (Hermes owns turn-end, FR-005) → `bridge.stt_transcribe` in `session.py` — depends on T008, T019
- [ ] T021 [US1] Session turn path: `bridge.agent_turn` (agent as entity, FR-004) → `bridge.tts_synthesize` → PCM→Opus (~24–32 kbps) outbound track in `session.py` — depends on T008, T019
- [ ] T022 [US1] Wire SC-001 latency telemetry (turn `started_at`/`ended_at`, `latency_ms`) into `ConversationTurn` + LogEntry — depends on T013, T021
- [ ] T023 [US1] FR-015 handling: typed error from bridge when all providers unavailable → session emits a perceptible failure (not silence/hang) — depends on T021

**Checkpoint**: MVP — a single real-time spoken conversation works end-to-end

---

## Phase 4: User Story 2 - Interrupt the agent mid-reply / barge-in (Priority: P2)

**Goal**: User speech during `speaking` stops playback ≤300 ms and the new
utterance becomes the next turn.

**Independent Test**: During FakeHermesBridge playback, inject inbound speech;
assert playback cancels ≤300 ms and the next reply addresses the interrupting
utterance.

### Tests for User Story 2

- [ ] T024 [P] [US2] Integration test `tests/integration/test_barge_in.py`: inbound speech during `speaking` cancels turn ≤300 ms (SC-003), no overlapping replies (FR-012)

### Implementation for User Story 2

- [ ] T025 [US2] Make `agent_turn`/`tts_synthesize` calls cancellable and add barge-in transition `speaking → listening` (cancel in-flight turn, mark outcome `interrupted`) in `src/hermes_satellite_adapter/session.py` — depends on T021
- [ ] T026 [P] [US2] Optional single SCTP datachannel on the voice PC for call-scoped UI only (partial transcript, listening/speaking, barge-in notice) — NO durable control here (constitution III) — in `src/hermes_satellite_adapter/session.py`

**Checkpoint**: US1 + US2 both independently functional

---

## Phase 5: User Story 3 - Operator monitors active voice sessions (Priority: P2)

**Goal**: Operator sees connected clients, per-session state, and per-session
logs via existing gateway surfaces.

**Independent Test**: With clients connected, `GET /satellite/list` and
`/satellite/{id}/state` reflect each session's live state; logs SSE returns
filterable per-session entries.

### Tests for User Story 3

- [ ] T027 [P] [US3] Contract test `tests/contract/test_list_state.py`: `/satellite/list` and `/satellite/{id}/state` reflect registry + live `VoiceSession.state`
- [ ] T028 [P] [US3] Contract test `tests/contract/test_logs_sse.py`: `/satellite/{id}/logs` and `/satellite/logs` stream `LogEntry`, filterable by `level`/`source`/`device_id`

### Implementation for User Story 3

- [ ] T029 [US3] Implement `GET /satellite/list`, `GET /satellite/{id}/state`, `DELETE /satellite/{id}` in `src/hermes_satellite_adapter/management.py` — depends on T017
- [ ] T030 [US3] Implement logs SSE `GET /satellite/{id}/logs` + aggregate `GET /satellite/logs` (filters) reading the gateway.log sink in `src/hermes_satellite_adapter/management.py` — depends on T013, T017
- [ ] T031 [US3] Broadcast `state_update`/`log_entry` over `WS /satellite/ws` to subscribed dashboard clients (`subscribe_device`/`unsubscribe_device`) — depends on T017

**Checkpoint**: US1 + US2 + US3 independently functional

---

## Phase 6: User Story 4 - Survive a dropped connection (Priority: P3)

**Goal**: Client network drop → automatic recovery without operator action or
gateway restart.

**Independent Test**: Drop control WS / voice ICE mid-session, restore; client
re-registers and a new conversation works without restarting the gateway.

### Tests for User Story 4

- [ ] T032 [P] [US4] Integration test `tests/integration/test_reconnect.py`: WS drop → `offline` on missed heartbeats → re-register restores `online`; ICE drop → Session teardown → re-offer establishes a new session (SC-007, FR-014)

### Implementation for User Story 4

- [ ] T033 [US4] Missed-heartbeat detection → `ConnectedClient.status=offline`, retain registry entry, accept re-`register` in `src/hermes_satellite_adapter/registry.py` + `management.py` — depends on T017
- [ ] T034 [US4] ICE/connection-state drop → tear down `VoiceSession`, free in-flight turn, keep client; accept fresh offer in `src/hermes_satellite_adapter/session.py` + `signaling.py` — depends on T018, T019
- [ ] T035 [US4] Gateway-restart behavior: active sessions end cleanly, clients re-register, no manual cleanup (verified via test harness restart) — depends on T033, T034

**Checkpoint**: All four user stories independently functional

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Contract completeness, performance validation, running-build gates

- [ ] T036 [P] Implement remaining management contract endpoints for completeness in `src/hermes_satellite_adapter/management.py`: `/satellite/{id}/config` GET/POST + `/config/schema` (push `config_changed` on WS), `/satellite/{id}/command`, OTA `/ota/check|apply|manifest` stubs (`browser` has no OTA) — contracts/management-api.md
- [ ] T037 Concurrency load test `tests/integration/test_concurrency.py`: ≥10 simultaneous sessions stay within 1.5× SC-001 latency (SC-005); full-pipeline load test before declaring viable (constitution V)
- [ ] T038 [P] Resolve verification gate VG-1/VG-2/VG-3: implement the real `HermesBridge` against the running Hermes build's STT/TTS provider interfaces, silence/end-of-utterance entrypoint, and shared adapter→agent entrypoint in `src/hermes_satellite_adapter/hermes_bridge.py` (only file that changes) — research.md
- [ ] T039 Resolve verification gate VG-4: implement the real adapter registration shim against the running Hermes platform-adapter base + confirm the enable/restart CLI surface in `src/hermes_satellite_adapter/adapter.py` — research.md
- [ ] T040 [P] Documentation: update `docs/` / package README with adapter setup; ensure CLAUDE.md plan reference current
- [ ] T041 Run `quickstart.md` end-to-end and confirm all listed checks pass

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (P1)**: no dependencies
- **Foundational (P2)**: depends on Setup — BLOCKS all user stories
- **User Stories (P3–P6)**: depend on Foundational; then independent of each other
- **Polish (P7)**: depends on the targeted user stories being complete

### User Story Dependencies

- **US1 (P1)**: after Foundational — no dependency on other stories (MVP)
- **US2 (P2)**: after Foundational; extends US1 session but independently testable
- **US3 (P2)**: after Foundational; reads registry/session state — independently testable
- **US4 (P3)**: after Foundational; independently testable

### Within Each User Story

- Tests written first and FAIL before implementation
- Models → registry/session → endpoints → integration
- Story complete before next priority

### Parallel Opportunities

- Setup: T003, T004 in parallel
- Foundational: T005, T006, T008, T009, T012 in parallel; T007/T010/T013 after their deps
- After Foundational, US1/US2/US3/US4 can be staffed in parallel
- Per story, all `[P]` test tasks run in parallel before implementation

---

## Parallel Example: User Story 1

```bash
# Tests for US1 together:
Task: "Contract test POST /satellite/register in tests/contract/test_register.py"
Task: "Contract test POST /webrtc/offer in tests/contract/test_webrtc_offer.py"
Task: "Integration P1 loop in tests/integration/test_p1_conversation.py"

# Foundational models/seam in parallel before US1:
Task: "Data models in src/hermes_satellite_adapter/models.py"
Task: "HermesBridge Protocol in src/hermes_satellite_adapter/hermes_bridge.py"
Task: "FakeHermesBridge in tests/conftest.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup → 2. Phase 2 Foundational → 3. Phase 3 US1 →
4. **STOP & VALIDATE** the P1 loop against FakeHermesBridge → 5. Demo MVP

### Incremental Delivery

Setup+Foundational → US1 (MVP) → US2 barge-in → US3 monitoring → US4
reconnect → Polish (concurrency + VG-1..VG-4 real Hermes wiring). Each story
adds value without breaking prior stories; the four verification gates are
isolated to T038/T039 so everything else ships against the fake bridge first.

### Parallel Team Strategy

Team does Setup+Foundational together; then Dev A → US1, Dev B → US3, Dev C →
US2, Dev D → US4; integrate independently.

---

## Notes

- `[P]` = different files, no incomplete dependencies
- Constitution gates encoded: I (T008/T012/T020/T021), II (T005), III
  (T017/T026), IV (T006/T013), V (T037/T038/T039)
- `hermes_bridge.py` is the only module touching Hermes intelligence — the
  running-build risk is contained to T038/T039
- Commit after each task or logical group; stop at any checkpoint to validate
