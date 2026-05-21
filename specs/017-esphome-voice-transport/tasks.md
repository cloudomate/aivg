---

description: "Task list — ESPHome Voice Assistant transport (feature 017)"
---

# Tasks: ESPHome Voice Assistant transport

**Input**: Design documents from `/specs/017-esphome-voice-transport/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/esphome-transport.md](./contracts/esphome-transport.md), [quickstart.md](./quickstart.md)

**Tests**: REQUIRED. The contract document § 8 enumerates 10 binding regression-gate tests. Test tasks are interleaved per user story.

**Organization**: Tasks are grouped by user story (US1 P1 MVP, US2 P1, US3 P1, US4 P2, US5 P3).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Maps to user stories in [spec.md](./spec.md#user-scenarios--testing-mandatory)
- All paths absolute from repo root `/Users/ys/coderepo/hermes-voice/`.

## Path Conventions

- Production code under `src/aivg_core/transports/esphome/` (new directory)
- Adapter wiring under `src/aivg_core/adapter.py` (+~15 LoC)
- Config schema under `src/aivg_core/config.py` (additive block)
- Tests under `tests/unit/`, `tests/integration/`, `tests/fixtures/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Pull in the upstream dependency and capture a clean pre-implementation baseline so the constitutional + parity gates (SC-002, SC-003, SC-005) have a binding reference.

- [X] T001 Add `aioesphomeapi>=23.0,<28.0` to the `dependencies` block in `pyproject.toml`. Verify `python -c "import aioesphomeapi.api_pb2; import aioesphomeapi.core; print('ok')"` succeeds in the Hermes venv after `pip install -e .`.
- [X] T002 Capture the pre-refactor full-suite baseline by running `for i in 1 2 3; do PYENV_VERSION=3.11.9 PYTHONPATH=src:tests pytest tests/ -q --tb=line 2>&1 | tail -3; echo "---"; done` and record the result in `specs/017-esphome-voice-transport/baseline.md` (new file). Expected: 290 passed across 3 runs.
- [X] T003 Capture the pre-refactor `aivg --contract-version` output in `baseline.md` (should be `1.0.0` — will bump to `1.1.0` in US5).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create the new module skeleton and the smallest deterministic units (framing, auth, media adapter, config schema) that ALL user stories will build on. None of these phases touch `Session` or `platforms/`.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 [P] Create directory `src/aivg_core/transports/__init__.py` (empty package marker; future-proofs for sibling transports beyond ESPHome).
- [X] T005 [P] Create directory `src/aivg_core/transports/esphome/__init__.py` exporting only `EsphomeTransport` (the public class). All other module symbols are plugin-internal.
- [X] T006 [P] Create `src/aivg_core/transports/esphome/framing.py` — thin wrapper around `aioesphomeapi.core.make_plain_text_packets()` for outbound serialization and `aioesphomeapi.core.bytes_to_varuint()` for inbound length-prefix decode. Exposes one async function `read_next_message(reader: asyncio.StreamReader) -> Tuple[int, bytes]` (opcode + raw payload) and one sync function `encode_message(msg) -> bytes`. ~50-80 LoC.
- [X] T007 [P] Create `src/aivg_core/transports/esphome/auth.py` with a `KeystoreResolver` class that reads `~/.aivg/devices/keys.json` (mode 0600), exposes `async def resolve(device_id: str) -> Optional[str]`, and a `verify(device_id, presented_password, bootstrap_key) -> bool` pure function. ~60-80 LoC.
- [X] T008 [P] Create `src/aivg_core/transports/esphome/media_adapter.py` defining `EsphomeMediaTransport` per [data-model.md § 3](./data-model.md#3-esphomemediatransport--the-seam-to-webrtcsession). Implements `MediaTransport` Protocol: `receive`, `send_audio`, `stop_playback`, `connection_state`, `close`. Plus `push_inbound`, `push_eof`, `drain_outbound` hooks for the connection co-routine. Includes `audioop.ratecv`-based 16k↔48k resampling. ~120-150 LoC.
- [X] T009 [P] In `src/aivg_core/config.py`: add `EsphomeTransportConfig` + `TransportsConfig` dataclasses per [data-model.md § 5](./data-model.md#5-config-schema-extension). Extend `SatelliteAdapterConfig` with `transports: TransportsConfig` (default-factory). Load from the YAML's `satellite.transports.esphome_api` block. ~30-50 LoC additive.
- [X] T010 [P] In `src/aivg_core/registry.py`: add `transport: str = "webrtc"` field to the device record dataclass (likely `Client` — verify class name in the file first). Default ensures existing devices stay tagged correctly. ~3 LoC.
- [X] T011 [P] In `src/aivg_core/models.py`: add `transport: str = "webrtc"` field to `VoiceSession` (and any other session-record class). Default ensures back-compat. ~3 LoC.
- [X] T012 Run smoke: `PYENV_VERSION=3.11.9 PYTHONPATH=src python -c "from aivg_core.transports.esphome import EsphomeTransport; from aivg_core.transports.esphome.media_adapter import EsphomeMediaTransport; from aivg_core.webrtc.session import MediaTransport; import aioesphomeapi.api_pb2 as pb; print('imports ok')"` — confirms the new module imports cleanly and the `MediaTransport` Protocol resolves.

### Phase 2 tests (run after T004-T012 complete)

- [X] T013 [P] Create `tests/unit/test_esphome_framing.py` with `test_varint_roundtrip` (encode + decode a `HelloRequest`, `ConnectRequest`, `VoiceAssistantAudio` via `framing.py`), `test_unknown_opcode_ignored` (drop and log only, no error). Per [contracts/esphome-transport.md § 8](./contracts/esphome-transport.md#8-contract-tests-binding) row 1-2.
- [X] T014 [P] Create `tests/unit/test_esphome_auth.py` with `test_valid_api_key_accepted` and `test_invalid_key_disconnects` (uses a temp-file keystore via `tmp_path`). Per contract § 8 row 3-4.
- [X] T015 [P] Create `tests/unit/test_esphome_media_adapter.py` with `test_protocol_membership` (`isinstance(em, MediaTransport)` — uses `runtime_checkable` if available, else a duck-type assertion against the five methods) and `test_resample_roundtrip` (48k → push_inbound → receive returns 48k bytes within RMS tolerance). Per contract § 8 row 5-6.
- [X] T016 Run `pytest -x tests/unit/test_esphome_framing.py tests/unit/test_esphome_auth.py tests/unit/test_esphome_media_adapter.py -v` — confirm all foundational unit tests pass.

**Checkpoint**: `aioesphomeapi` is on the path; framing + auth + media-adapter all green; config + registry schema-extended. Adapter wiring is still NOT touched — that's US1.

---

## Phase 3: User Story 1 — HA Voice PE box runs against AIVG end-to-end (Priority: P1) 🎯 MVP

**Goal**: A Home Assistant Voice Preview Edition device (or any ESPHome voice satellite) registers with AIVG via the new TCP listener, completes one full voice turn (mic → STT → agent → TTS → speaker), and disconnects cleanly. The transport is wired into `adapter.py` and routes through the existing `Session` via `EsphomeMediaTransport`.

**Independent Test**: an in-process protobuf-client fixture connects to a running `EsphomeTransport` instance, completes one turn against the echo platform fixture, and the captured outbound audio matches echo's deterministic synth output.

### Implementation for User Story 1

- [X] T017 [US1] Create `src/aivg_core/transports/esphome/voice_protocol.py` with the per-pipeline-event helpers: `handle_voice_request(conn, req) -> VoiceAssistantResponse`, `emit_event(conn, event_type, data=None)` (one outbound `VoiceAssistantEventResponse`), `handle_voice_audio(conn, audio_frame)` (push into media adapter), `handle_voice_config(conn, req) -> VoiceAssistantConfigurationResponse` (advertise 16 kHz mono PCM, wake-word=none, codec=raw). Maps every event per [research.md R-4](./research.md#r-4--voice-assistant-pipeline-event-mapping-implementation-note). ~150-200 LoC.
- [X] T018 [US1] Create `src/aivg_core/transports/esphome/connection.py` with `EsphomeConnection` per [data-model.md § 2](./data-model.md#2-esphomeconnection--per-device-task-body). Implements the state machine (`HANDSHAKING → AUTHING → READY → VOICE_ACTIVE → CLOSING → CLOSED`) with one method per transition: `_handshake`, `_authenticate`, `_serve_voice`, `_close`. Owns the per-device `Session` instance constructed against `EsphomeMediaTransport`. ~200-250 LoC.
- [X] T019 [US1] Create `src/aivg_core/transports/esphome/server.py` with `EsphomeServer` (or fold into `__init__.py`): wraps `asyncio.start_server` + `_on_connect` callback that spawns one `asyncio.Task(EsphomeConnection.run())` per accepted socket. Owns the listener socket + the task registry. ~80-120 LoC.
- [X] T020 [US1] Wire `EsphomeTransport` (the public class in `__init__.py`) as the composition point: takes `registry, platform, sink, host, port, api_key_resolver, ui_broadcast`; exposes `start()` and `stop()`; delegates to the server. ~60-80 LoC.
- [X] T021 [US1] In `src/aivg_core/adapter.py`: after the existing two aiohttp sites in `SatelliteWebRTCAdapter.start()`, add a conditional ~15-line block that, if `self.cfg.transports.esphome_api.enabled` is `True`, constructs and starts an `EsphomeTransport`. Store the instance on `self._esphome_transport`. In `stop()`, gracefully stop it (mirror the existing site-runner cleanup). Per [data-model.md § 8](./data-model.md#8-adapter-wiring-change). Verify the wiring with `grep -n 'esphome' src/aivg_core/adapter.py | head` afterwards.
- [X] T022 [US1] Add an `api_key_resolver` helper to `adapter.py` (or a small new file `src/aivg_core/transports/esphome/keystore_hook.py`) that constructs the `KeystoreResolver` from `~/.aivg/devices/keys.json` and wires it into `EsphomeTransport`. The `bootstrap_key` config field (if set) is honoured here. ~30 LoC.

### Test fixture (US1) — in-process ESPHome client

- [X] T023 [P] [US1] Create `tests/fixtures/esphome_client.py` — an in-process minimal ESPHome protocol client that connects via `asyncio.StreamReader/Writer` (or in-memory pipe pair) and exposes async methods: `connect_and_auth(api_key)`, `start_voice_pipeline()`, `send_audio_frame(pcm)`, `mark_endpoint()`, `recv_event() -> str`, `recv_audio() -> bytes`, `disconnect()`. Speaks the real `aioesphomeapi.api_pb2` shapes via the `framing.py` helpers. Uses `aioesphomeapi.api_pb2.HelloRequest` etc. directly. ~150-200 LoC.

### Tests for User Story 1

- [X] T024 [P] [US1] Create `tests/integration/test_esphome_transport_basic.py` with `test_one_turn_against_echo_platform`: load the echo platform fixture (via the same `spec_from_file_location` trick as feature 015's tests), construct `EsphomeTransport(platform=echo)`, start on an ephemeral port, connect the in-process client, drive one turn, assert that the captured reply audio matches `echo:synth(...)` deterministically. **ZERO** Hermes import in the test (asserted by an `ast` walk at the end of the test). Per contract § 8 row 7.
- [X] T025 [US1] Run `pytest -x tests/integration/test_esphome_transport_basic.py -v` and confirm one turn completes end-to-end against the echo platform.

**Checkpoint**: a non-Hermes plugin drives one voice turn through the new ESPHome transport. US1 is satisfied. Now verify US2 (WebRTC clients still work) and US3 (constitutional gate).

---

## Phase 4: User Story 2 — WebRTC clients keep working (Priority: P1)

**Goal**: The TS SDK (`@aivg/sat-sdk` 0.1.3) electron-test smoke succeeds against the post-017 gateway with zero rebuilds. The contract version bumps `1.0.0` → `1.1.0` (additive) but same-major compatibility holds.

**Independent Test**: the existing electron-test flow + the existing feature-014/015 integration tests all pass; `aivg --contract-version` returns `1.1.0` with `transports: ["webrtc", "esphome_api"]`.

### Implementation for User Story 2

- [X] T026 [US2] In whatever file emits the `aivg --contract-version` JSON envelope (search via `rg -n 'contract_version' src/aivg_core/`), bump the value from `"1.0.0"` to `"1.1.0"` and add a `"transports": ["webrtc", "esphome_api"]` field. The `transports` array MUST list only the transports whose listeners are actually bound (so a `transports.esphome_api.enabled=false` deployment emits `["webrtc"]` only). Per [spec.md FR-016](./spec.md#contract-versioning).
- [X] T027 [US2] In the same file (or a sibling), confirm the SDK-compatibility-check semantics: a minor bump (`1.0.0` → `1.1.0`) MUST NOT trigger a "version mismatch" warning in any consumer code. Verify via `rg -n '1\.0\.0' src/aivg_core/` that no hardcoded equality check exists.

### Tests for User Story 2

- [X] T028 [P] [US2] Run the full existing test suite three consecutive times: `for i in 1 2 3; do PYENV_VERSION=3.11.9 PYTHONPATH=src:tests pytest tests/ -q --tb=line 2>&1 | tail -3; echo "---"; done`. Expected: 290+ passed every run, zero failures, zero new flakes. Per spec SC-002 / SC-004.
- [X] T029 [US2] Live smoke: launch the gateway with `transports.esphome_api.enabled: true` in `~/.satellite/config.yaml`, restart, then run `clients/electron-test` (PTT round-trip). Confirm the electron-test client (`@aivg/sat-sdk 0.1.3`) successfully completes one voice turn — same flow as feature 014's live smoke. Record outcome in `baseline.md`. Per spec SC-002.
- [X] T030 [US2] Confirm `aivg --contract-version` returns `{"contract_version":"1.1.0","transports":["webrtc","esphome_api"]}` (or equivalent) when the new transport is enabled. Record in `baseline.md`.

**Checkpoint**: WebRTC clients are byte-identical post-017. Wire-surface invariance gate satisfied.

---

## Phase 5: User Story 3 — One AgentPlatform, two transports (Priority: P1 — constitutional gate)

**Goal**: ZERO modifications to `src/aivg_core/platforms/`. The Hermes plugin (and any future plugin) is unchanged. The new transport reaches `AgentPlatform` verbs **only** through `Session`, never via direct import of any `platforms/` symbol.

**Independent Test**: `tests/unit/test_no_transport_imports_in_platforms.py` and `git diff` against feature 015's branch HEAD both confirm zero plugin-directory edits in the 017 range.

### Tests for User Story 3 (grep-gate regression boundary)

- [X] T031 [P] [US3] Create `tests/unit/test_no_transport_imports_in_platforms.py` with `test_no_transport_imports_in_platforms`: uses `subprocess.run(["rg", "-n", "from .*transports\\.esphome", "src/aivg_core/platforms/"], …)` and asserts exit code 1 (zero matches). Mirrors the feature-015 grep gates. Per [contract § 8](./contracts/esphome-transport.md#8-contract-tests-binding) row 10 + spec SC-005.
- [X] T032 [P] [US3] Add a sibling test `test_no_session_modifications_in_017_range` (in the same file or `tests/unit/test_no_session_modifications.py`): `subprocess.run(["git", "diff", "015-agentplatform-runtime-closure...HEAD", "--", "src/aivg_core/webrtc/session.py"], …)` and assert empty output. Tolerates any feature branch base via configurable git ref. Per spec FR-009.
- [X] T033 [P] [US3] Add `test_no_platforms_modifications_in_017_range` (same pattern as T032 but for `src/aivg_core/platforms/`). Per spec SC-003.
- [X] T034 [US3] Run `pytest -x tests/unit/test_no_transport_imports_in_platforms.py tests/unit/test_no_session_modifications.py -v` and confirm all three constitutional grep gates pass.

**Checkpoint**: Constitutional Principle IV is grep-gate-enforced. The next refactor that re-introduces a `platforms/`-touching coupling fails CI.

---

## Phase 6: User Story 4 — Multi-device concurrency (Priority: P2)

**Goal**: Four ESPHome devices simultaneously each complete one voice turn within 1.5× single-device latency. One `asyncio.Task` per device (R-2); no shared state contention between devices.

**Independent Test**: a parametrised integration test runs N=4 concurrent in-process clients and asserts all four complete within budget.

### Tests for User Story 4

- [X] T035 [P] [US4] Create `tests/integration/test_esphome_multi_device.py` with `test_four_concurrent_turns`: spawn 4 in-process ESPHome clients (using the fixture from T023), connect to a single `EsphomeTransport` on an ephemeral port, each runs one turn against the echo platform concurrently via `asyncio.gather`. Assert: all 4 captured reply audios match echo's deterministic output; max per-task wall-clock ≤ 1.5 × the single-task budget. Per contract § 8 row 8 + spec SC-006.
- [X] T036 [US4] Run `pytest -x tests/integration/test_esphome_multi_device.py -v --count=3` (or three sequential `pytest` invocations) to confirm 3 consecutive green runs (mirrors feature-015's stability bar for concurrency tests).

### Tests for User Story 4 — resource hygiene (FR-021)

- [X] T037 [P] [US4] Create `tests/integration/test_esphome_disconnect_cleanup.py` with `test_no_task_leak`: open 100 ESPHome sessions sequentially, each drops mid-turn (sends partial audio then closes the writer); after 5 s assert `len(asyncio.all_tasks())` returns to baseline ± a small tolerance. Per contract § 8 row 9 + spec SC-007.
- [X] T038 [US4] Run `pytest -x tests/integration/test_esphome_disconnect_cleanup.py -v` and confirm no task leak.

**Checkpoint**: Multi-device + resource-hygiene gates green. The transport scales to v1's homelab device count without contention.

---

## Phase 7: User Story 5 — Management plane shows ESPHome devices (Priority: P3)

**Goal**: `aivg list` and the management-plane WS state updates show ESPHome devices alongside WebRTC devices, with a `transport` discriminator. Operator's mental model is "one gateway, N devices."

**Independent Test**: a multi-transport integration test confirms `aivg list` output schema gains the `transport` field and ESPHome devices appear in it.

### Implementation for User Story 5

- [X] T039 [US5] In whatever file emits the `aivg list` REST response (search `rg -n '/devices' src/aivg_core/management/`), add the `transport` field to each device record in the output schema. Defaults to `"webrtc"` for existing devices (the registry field added in T010 handles this); ESPHome devices get `"esphome_api"`. Per spec FR-013.
- [X] T040 [US5] In the management-plane WS broadcaster (`src/aivg_core/management/service.py` `_broadcast` or equivalent), include the `transport` field in the `state_update` payload. Per spec FR-014.
- [X] T041 [US5] In `src/aivg_core/logsink.py` (or the JSON envelope emitter), ensure ESPHome-source log entries carry `source: "esphome"` (or an additional `transport: "esphome_api"` field). Verify by greping the gateway log after an ESPHome turn. Per spec FR-015.
- [X] T042 [US5] In `aivg` CLI's `list` subcommand (find via `rg -n 'def list' src/aivg/cli.py` or wherever the CLI lives), add a `transport` column to the table output. Per spec FR-013.

### Tests for User Story 5

- [X] T043 [P] [US5] Create `tests/integration/test_management_shows_esphome_devices.py`: register one WebRTC device and one ESPHome device (via the in-process fixture), then call the management plane's `/devices` endpoint and assert both appear with the correct `transport` field. Per spec US5 acceptance scenarios.
- [X] T044 [US5] Run `pytest -x tests/integration/test_management_shows_esphome_devices.py -v` and confirm the discriminator surfaces correctly.

**Checkpoint**: Operator surfaces show ESPHome devices as first-class citizens.

---

## Phase 8: Polish & Live-Host Verification

- [X] T045 [P] Update `specs/017-esphome-voice-transport/quickstart.md` § 5 (electron-test smoke) with the actual measured outcome from T029. Update § 6 (live ESPHome smoke) with any device-specific YAML adjustments discovered during T046.
- [ ] T046 **Live host smoke** (binding SC-001 gate): on the Hermes host, point a real ESPHome voice satellite (Home Assistant Voice Preview Edition, M5Stack Atom Echo, or any device flashed with the upstream voice-assistant YAML) at the post-017 AIVG gateway. Run `aivg device adopt <device_id> --transport esphome_api`, paste the generated API key into the device's ESPHome `api: password:`, reflash. Confirm: device appears in `aivg list` within 5 s; one full voice turn (mic → STT → agent → TTS → speaker) completes within 30 s. Record outcome in `baseline.md`.
- [X] T047 [P] Run the full quickstart end-to-end (all 9 steps in [quickstart.md](./quickstart.md)) against the post-017 gateway. Every step MUST pass without manual fix-up. Note any docs-drift in T045.
- [X] T048 [P] Update [CLAUDE.md](../../CLAUDE.md) "prior features" list to mark feature 017 as `[implemented + live-proven]` once T046 + T029 pass.
- [X] T049 Add a brief implementation summary section to [plan.md](./plan.md) (`## Implementation Outcome`) capturing: net LoC change (`git diff --stat 015-agentplatform-runtime-closure...HEAD -- src/`), test-count delta, measured WebRTC turn vs ESPHome turn latency comparison, and any deviations from the plan worth noting for the next refactor (especially anything that nudged R-3's "no `Session` changes" rule).
- [X] T050 [P] Commit-time check: run `aivg --contract-version` and confirm it prints `1.1.0` with the transports array (SC-002 / FR-016). Confirm `git diff main...HEAD -- src/aivg_core/platforms/ | wc -l` is `0` (SC-003 / SC-005). Both numbers go into the final commit message.

---

## Dependencies & Execution Order

**Phase order (strict)**: Phase 1 (Setup) → Phase 2 (Foundational) → Phase 3 (US1 — MVP). After US1 lands, **Phases 4 (US2), 5 (US3), 6 (US4), 7 (US5) can be implemented in parallel** because they are read-mostly / test-mostly with disjoint file targets. Phase 8 (Polish) runs last.

**User-story dependency graph**:

```text
Phase 1 (Setup) → Phase 2 (Foundational)
                       │
                       ▼
                  US1 (P1 — wiring + first integration test)
                       │
       ┌───────────────┼───────────────┬───────────────┐
       ▼               ▼               ▼               ▼
  US2 (P1)         US3 (P1)        US4 (P2)        US5 (P3)
  WebRTC parity    Const grep      Concurrency     Mgmt plane
       │               │               │               │
       └───────────────┴───────────────┴───────────────┘
                                    │
                                    ▼
                               Phase 8 (Polish)
```

**Within-phase dependencies**:

- **Phase 2**: T004 + T005 (directories) must precede T006-T011 (files). T013-T015 (tests) follow T006-T011.
- **Phase 3 (US1)**: T017 → T018 → T019 → T020 → T021 → T022 (file-by-file, sequential — they touch the same package). T023 (fixture) parallel to T017-T022. T024 follows T022. T025 follows T024.
- **Phase 4 (US2)**: T026 → T027 → T028 → T029 → T030 (mostly verification — each builds on the previous).
- **Phase 7 (US5)**: T039 / T040 / T041 / T042 touch different files → parallel. T043 follows them.

## Parallel Execution Examples

**After T012 (foundational done)** — kick off all five foundational tests concurrently:

```bash
worker A: T013 (test_esphome_framing.py)
worker B: T014 (test_esphome_auth.py)
worker C: T015 (test_esphome_media_adapter.py)
# then T016 (run them all)
```

**After T025 (US1 done)** — four user-story tracks in parallel:

```bash
worker D (US2): T026 → T027 → T028 → T029 → T030
worker E (US3): T031 || T032 || T033 (parallel), then T034
worker F (US4): T035 → T036, T037 → T038
worker G (US5): T039 || T040 || T041 || T042 (parallel), then T043 → T044
```

## Implementation Strategy

**MVP**: T001-T012 (Setup + Foundational) + T017-T025 (US1). This is **21 tasks** that get one ESPHome voice satellite talking to AIVG end-to-end through the echo platform. Even if US2-US5 slipped, the binding "ESPHome support exists" claim would hold.

**Full delivery**: All eight phases (50 tasks). US2 is the regression-protection gate (no WebRTC breakage); US3 is the constitutional gate (grep-enforced); US4 is the scale gate; US5 is the operator-UX polish. Phase 8 captures the live receipts (the key gate is T046 — a real ESPHome device against a real AIVG gateway).

**Risk mitigation**: T002 baseline must complete BEFORE any production code edit. SC-002 (electron-test parity) is non-negotiable; without the recorded baseline T029's pass/fail signal is hand-wavy.

## Format Validation

All 50 tasks above conform to `- [ ] T### [P?] [Story?] description with file path`. Story labels appear only on Phase 3-7 tasks (T017-T044); Phase 1 (T001-T003), Phase 2 (T004-T016), and Phase 8 (T045-T050) are unlabelled per the rules. Every task description names an exact file path or a precise verifiable command.
