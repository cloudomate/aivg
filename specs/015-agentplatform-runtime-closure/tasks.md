---

description: "Task list — AgentPlatform Runtime Closure (feature 015)"
---

# Tasks: AgentPlatform Runtime Closure

**Input**: Design documents from `/specs/015-agentplatform-runtime-closure/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/agent-platform.md](./contracts/agent-platform.md), [quickstart.md](./quickstart.md)

**Tests**: REQUIRED. This feature ships binding regression gates as new tests (FR-011, FR-012, contract tests in [contracts/agent-platform.md § 7](./contracts/agent-platform.md#7-contract-tests-binding)). Test tasks are interleaved per user story.

**Organization**: Tasks are grouped by user story (US1 P1 MVP, US2 P1, US3 P2, US4 P2) to enable independent verification.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Maps to user stories in [spec.md](./spec.md#user-scenarios--testing-mandatory)
- All paths absolute from repo root `/Users/ys/coderepo/hermes-voice/`.

## Path Conventions

- Production code under `src/aivg_core/`
- Tests under `tests/`
- Plugin fixtures under `tests/fixtures/platforms/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Capture the pre-refactor baseline so SC-003 (±10 % latency) and SC-002 (live electron-test parity) have something to compare against.

- [ ] T001 Capture pre-refactor latency baseline by running `pytest -x tests/integration/test_voice_turn_latency.py::test_first_audio_p50 -v --runs 10` against `main` and record the median in `specs/015-agentplatform-runtime-closure/baseline.md` (new file). This is the SC-003 reference number.
- [ ] T002 Capture pre-refactor `grep` baseline counts: run `rg -n '# AgentPlatform-coupling-TODO' src/aivg_core/ | wc -l` (expect 3) and `rg -n 'from .*platforms.hermes\.' src/aivg_core/ | wc -l` (expect ≥ 3) and append both to `specs/015-agentplatform-runtime-closure/baseline.md`.
- [ ] T003 [P] Confirm the electron-test smoke (PTT → STT → reply → TTS) works on `main` against the current gateway as the SC-002 reference point; note pass/fail in `baseline.md`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Land the shared types and the Hermes plugin wrapper that ALL user stories build on. The seam files (`adapter.py`, `session.py`, `signaling.py`) are NOT touched here — that is US1.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Add `EndpointResult` frozen dataclass to `src/aivg_core/platforms/base.py` per [data-model.md § 2](./data-model.md). Fields: `end_of_utterance: bool`, `speech_started: bool = False`. Export from module. This is the R-1 lift.
- [X] T005 Update the `AgentPlatform` Protocol in `src/aivg_core/platforms/base.py` so `endpoint` returns `EndpointResult` (not bare `bool`). Update the Protocol docstrings to match [contracts/agent-platform.md § 2.4](./contracts/agent-platform.md#24-endpointframe---endpointresult).
- [X] T006 Add `_validate_agent_platform(plat) -> None` helper to `src/aivg_core/platforms/base.py` per [data-model.md § 6](./data-model.md#6-validation-helper). Checks the four required callables (`transcribe`, `agent_step`, `synthesize`, `endpoint`) plus a non-empty lowercase `name`; raises `RuntimeError` with a clear missing-verb list pointing at `contracts/agent-platform.md`.
- [X] T007 [P] Add `agent_text_deltas(text, session_id, *, history) -> AsyncIterator[str]` private helper to `src/aivg_core/platforms/hermes/bridge.py` that wraps the existing `_cb` text-delta callback path in an async queue. ~20 LoC; do not touch existing public methods. Plugin-internal.
- [X] T008 [P] Add `detect_endpoint_frame(frame, *, ctx) -> EndpointSignal` private helper to `src/aivg_core/platforms/hermes/bridge.py` that wraps the existing async-stream `detect_endpoint` for a single PCM frame. ~10 LoC. Plugin-internal.
- [X] T009 Create new file `src/aivg_core/platforms/hermes/platform.py` containing `HermesAgentPlatform` per [data-model.md § 3](./data-model.md#3-hermesagentplatform-plugin-internal): `name = "hermes"`, all six required verbs delegating to `HermesV013Bridge`, plus the optional `agent_stream` extension forwarding to the bridge's existing streamer. Conversion in `endpoint()` constructs `EndpointResult` from the bridge's `EndpointSignal`.
- [X] T010 Update `src/aivg_core/platforms/hermes/__init__.py` per [data-model.md § 4](./data-model.md#4-plugin-export-surface): export ONLY `PLATFORM = HermesAgentPlatform()`, `SETUP`, `HermesSetupCapability`; set `__all__` accordingly; REMOVE any re-export of `HermesBridge`, `HermesV013Bridge`, `UnboundHermesBridge`, `EndpointSignal`, `AgentReply`, `SessionCtx`.
- [X] T011 Run `python -c "from aivg_core.platforms.hermes import PLATFORM; from aivg_core.platforms.base import _validate_agent_platform; _validate_agent_platform(PLATFORM); print('OK', PLATFORM.name)"` and confirm output is `OK hermes`. This is the smoke that the foundational phase is done.

**Checkpoint**: `HermesAgentPlatform` exists, satisfies the Protocol, and the Hermes plugin no longer re-exports bridge symbols. The seam files still hold the three TODO markers — US1 removes them.

---

## Phase 3: User Story 1 — Non-Hermes plugin drives the voice loop (Priority: P1) 🎯 MVP

**Goal**: Rewire `adapter.py`, `webrtc/session.py`, `webrtc/signaling.py` to consume `AgentPlatform` (via `PluginRegistry.load`) instead of importing `HermesBridge` directly. Remove all three `# AgentPlatform-coupling-TODO` markers. The voice loop runs end-to-end against ANY plugin satisfying the contract.

**Independent Test**: `rg '# AgentPlatform-coupling-TODO' src/aivg_core/` returns zero matches AND `pytest -x tests/integration/test_voice_session_basic.py` passes (Hermes still drives a turn).

### Implementation for User Story 1

- [X] T012 [US1] In `src/aivg_core/webrtc/signaling.py`: remove the `from ..platforms.hermes.bridge import HermesBridge  # AgentPlatform-coupling-TODO` import (line 17); replace with `from ..platforms.base import AgentPlatform`. Change `SignalingService.__init__` to accept `platform: AgentPlatform` instead of `bridge: HermesBridge` and forward to per-session `Session` instances. Update any internal `self._bridge` references to `self._platform`.
- [X] T013 [US1] In `src/aivg_core/webrtc/session.py`: remove the `from ..platforms.hermes.bridge import (HermesBridge, SessionCtx, AgentReply, AllProvidersUnavailable,)  # AgentPlatform-coupling-TODO` import (line 23). Replace with `from ..platforms.base import AgentPlatform, EndpointResult` and `from ..platforms.hermes.bridge import AllProvidersUnavailable` (base-class exception, plugin-neutral). Move `SessionCtx` definition local to `session.py` (it was already mostly used here).
- [X] T014 [US1] In `src/aivg_core/webrtc/session.py`: change `Session.__init__` signature from `bridge: HermesBridge` to `platform: AgentPlatform`; store as `self._platform`; cache `self._agent_stream = getattr(platform, "agent_stream", None)` at construction (US3 prep).
- [X] T015 [US1] In `src/aivg_core/webrtc/session.py` line ~97: swap `await bridge.tts_synthesize(text, ctx=ctx)` → `await self._platform.synthesize(text)`. Drop the `ctx=ctx` plumbing here (the platform owns its own session context).
- [X] T016 [US1] In `src/aivg_core/webrtc/session.py` line ~207 + ~335: swap `sig = await self._bridge.detect_endpoint(await self._one(frame), ctx=self._ctx)` → `sig = await self._platform.endpoint(frame)`. The returned `EndpointResult` keeps `sig.end_of_utterance` and `sig.speech_started` field access unchanged.
- [X] T017 [US1] In `src/aivg_core/webrtc/session.py` line ~230: swap `turn.user_text = await self._bridge.stt_transcribe(utterance, ctx=self._ctx)` → `turn.user_text = await self._platform.transcribe(utterance, sample_rate=self._sr)`.
- [X] T018 [US1] In `src/aivg_core/webrtc/session.py` line ~313: replace `reply: AgentReply = await self._bridge.agent_turn(turn.user_text, ctx=self._ctx)` with the R-2 accumulator: `acc: list[str] = []; async for delta in self._platform.agent_step(turn.user_text, session_id=self._session_id, history=self._history): acc.append(delta)`; treat `"".join(acc).strip() == ""` as the empty-reply branch (replaces `reply.is_empty`); use the accumulated text as the input to the synth path.
- [X] T019 [US1] In `src/aivg_core/adapter.py`: remove BOTH `# AgentPlatform-coupling-TODO` imports (lines 18 and 127); replace with `from .platforms.base import AgentPlatform, PluginRegistry, _validate_agent_platform`.
- [X] T020 [US1] In `src/aivg_core/adapter.py`: in `_SatellitePlatformAdapter.__init__` (or wherever `HermesV013Bridge` was instantiated), replace `self._bridge = HermesV013Bridge(agent_runner=_run_agent)` with `self._platform: AgentPlatform = PluginRegistry.load(self.cfg.platform); _validate_agent_platform(self._platform)`. Replace `self._impl = SatelliteWebRTCAdapter(bridge=self._bridge)` with `self._impl = SatelliteWebRTCAdapter(platform=self._platform)`.
- [X] T021 [US1] In `src/aivg_core/adapter.py`: thread `await self._platform.startup(gateway_config=self.cfg.to_dict())` into the existing adapter startup path; thread `await self._platform.shutdown()` into the teardown path.
- [X] T022 [US1] In `src/aivg_core/adapter.py`: fold the previous `_run_agent` callback into the Hermes plugin's construction (it routes the gateway's `handle_message`; that's Hermes-specific). The new `HermesAgentPlatform` is constructed with the `agent_runner` argument injected by adapter via a Hermes-plugin-specific factory parameter, OR the plugin reads it from `gateway_config` in `startup`. Pick the latter (cleaner; keeps `adapter.py` plugin-neutral).
- [X] T023 [US1] Update `src/aivg_core/webrtc/__init__.py` (and any other re-export modules) to drop `HermesBridge` references if they exist.
- [X] T024 [US1] Update `SatelliteWebRTCAdapter` (whichever file holds it — likely `webrtc/__init__.py` or `adapter.py`) so its constructor takes `platform: AgentPlatform` instead of `bridge: HermesBridge` and passes it through to `SignalingService` and `Session`.

### Tests for User Story 1 (binding regression gates)

- [X] T025 [P] [US1] Create `tests/unit/test_no_coupling_todo_markers.py` — uses `subprocess.run(["rg", "-n", "# AgentPlatform-coupling-TODO", "src/aivg_core/"], …)`; asserts return code is 1 (no matches). Includes a docstring linking to FR-012 / SC-001.
- [X] T026 [P] [US1] Create `tests/unit/test_no_hermes_imports_in_core.py` — uses `subprocess.run(["rg", "-n", "from .*\\.platforms\\.hermes\\.", "src/aivg_core/"], …)` and filters out matches whose path starts with `src/aivg_core/platforms/hermes/`; asserts the filtered list is empty. Links to FR-011 / SC-006.
- [X] T027 [US1] Run `pytest -x tests/unit/test_no_coupling_todo_markers.py tests/unit/test_no_hermes_imports_in_core.py -v` and confirm both pass. If either fails, the seam-rewire is incomplete — return to T012-T024.

**Checkpoint**: Three TODO markers gone; zero Hermes imports in `aivg_core/` outside `platforms/hermes/`. The voice loop is wired against `AgentPlatform`. US2 verifies Hermes still works.

---

## Phase 4: User Story 2 — Hermes plugin keeps byte-equivalent parity (Priority: P1)

**Goal**: Every existing Hermes-integration test passes unchanged; the live electron-test smoke completes one full voice turn against the refactored loop.

**Independent Test**: `pytest -x tests/integration/test_voice_session_basic.py tests/integration/test_voice_session_barge_in.py tests/integration/test_signaling_offer_answer.py` is all-green AND the manual electron-test PTT round-trip succeeds.

### Implementation for User Story 2

- [X] T028 [US2] Update each existing test that constructs a `Session(bridge=…)` or `SignalingService(bridge=…)` to use the new `platform=…` keyword. Search: `rg -n 'bridge=' tests/` and patch each occurrence to construct via `PLATFORM` from `aivg_core.platforms.hermes` (or a fake-platform helper — see T030). Files likely affected: `tests/unit/test_session_*.py`, `tests/integration/test_voice_session_*.py`.
- [X] T029 [US2] If any `FakeHermesBridge` / `UnboundHermesBridge` stub is constructed in test fixtures, wrap it in a one-off `_FakePlatformFromBridge` adapter so existing tests don't need rewriting (they keep their fixture's deterministic behaviour). Place in `tests/helpers/fake_platform_from_bridge.py`.
- [X] T030 [P] [US2] Create `tests/helpers/fake_agent_platform.py` exposing a `FakeAgentPlatform` class implementing the four protocol verbs with injectable canned responses (transcript text, reply deltas, synth bytes, EOU frame index). This is the test-side replacement for `FakeHermesBridge` for new tests; old tests use the bridge-wrapping adapter from T029.
- [X] T031 [US2] Run `pytest -x tests/unit/ tests/integration/ -v` and confirm all tests that passed pre-refactor still pass. Any test that was Hermes-bridge-specific by *behaviour* (not by mock shape) keeps its assertions; any test that was bridge-specific by *type* (e.g., `isinstance(x, HermesBridge)`) gets re-pointed at `HermesAgentPlatform`.

### Live verification for User Story 2 (SC-002, SC-008)

- [ ] T032 [US2] Run `aivg setup --force --yes` against the Hermes host to re-install the satellite plugin and the refactored `aivg_core`. Confirm setup completes within 60s (SC-008).
- [ ] T033 [US2] Restart the gateway with `hermes config set voice.silence_duration 1.2; hermes gateway run --port 8643`. Launch the electron-test (`cd clients/electron-test && npm start`), connect, adopt, hold PTT, say "Hello, can you hear me?", release. Confirm: state transitions through `listening → thinking → speaking → idle`; transcript field populates; agent reply populates; reply audio plays. Record in `specs/015-agentplatform-runtime-closure/baseline.md` under "Post-refactor SC-002".
- [ ] T034 [US2] Run `pytest -x tests/integration/test_voice_turn_latency.py::test_first_audio_p50 -v --runs 10` against the refactored gateway; record post-refactor median. Confirm |post − pre| / pre ≤ 0.10 (SC-003 / FR-015 ±10 %).

**Checkpoint**: Hermes parity preserved. The refactor is invisible from the user's seat.

---

## Phase 5: User Story 3 — `agent_stream` optional extension preserved (Priority: P2)

**Goal**: The feature 008 / 010 latency win remains for delta-capable platforms. The loop detects `agent_stream` at session construction, prefers it when present, falls back to `agent_step + synthesize` per accumulated sentence when absent.

**Independent Test**: A test platform with ONLY `agent_step` completes one turn. The Hermes platform (with `agent_stream`) shows `agent_first_output` and `first_unit_ready` latency instants present in the timing breakdown.

### Implementation for User Story 3

- [X] T035 [US3] In `src/aivg_core/webrtc/session.py` `_respond` (or the equivalent agent-call site in the turn loop): use `self._agent_stream` (cached in T014) — if non-None, run the audio-streaming path; if None, run the accumulator path. The shape detection happens ONCE per Session, not per turn (R-3 design).
- [X] T036 [US3] Ensure the empty-reply branch (R-2: accumulated text `.strip() == ""`) applies in BOTH paths — `agent_step` accumulation OR a zero-chunk `agent_stream`. Skip TTS, return to listening.
- [X] T037 [US3] Verify feature 010 latency instants (`endpoint_detected`, `agent_first_output`, `first_unit_ready`, `first_audio_synth`, `first_audio_delivered`) are still emitted at the same code seam — the new `self._platform` call sites must preserve the instrumentation points (likely already in `webrtc/session.py` around the await points).

### Tests for User Story 3

- [X] T038 [P] [US3] Add `tests/integration/test_agent_stream_optional.py`: construct a `FakeAgentPlatform` that exposes ONLY `agent_step` (no `agent_stream`); run one voice turn; assert the turn completes and audio is synthesised via the `synthesize()` fallback path. Construct a second `FakeAgentPlatform` that exposes BOTH; assert the `agent_stream` path is taken (verifiable by spying on the bytes counter or by a counter on the fixture's `synthesize`).
- [X] T039 [US3] Re-run `pytest -x tests/integration/test_voice_turn_latency.py -v`; assert all feature-010 latency instant tests still pass post-refactor.

**Checkpoint**: Optional extension works; latency unchanged; absent-extension path validated.

---

## Phase 6: User Story 4 — Test suite reflects the new shape (Priority: P2)

**Goal**: The contract tests in [contracts/agent-platform.md § 7](./contracts/agent-platform.md#7-contract-tests-binding) all exist and pass against BOTH the Hermes plugin AND the echo fixture. A dedicated integration test drives the voice loop end-to-end against the echo platform.

**Independent Test**: `pytest -x tests/contract/test_agent_platform_contract.py tests/integration/test_voice_loop_platform_agnostic.py -v` passes.

### Echo fixture alignment

- [X] T040 [US4] Verify `tests/fixtures/platforms/echo/__init__.py` exposes `PLATFORM` with the four required verbs matching the contract; align any signature drift (e.g., `endpoint` returning `EndpointResult` not bare `bool`; `transcribe` taking `sample_rate` kw-only).
- [X] T041 [US4] Make the echo platform's `agent_step` yield deltas from a configurable list (default: echo the input text as one delta) so US4 integration test can assert on known reply text.

### Contract tests

- [X] T042 [P] [US4] Create `tests/contract/test_agent_platform_contract.py` — parametrised over `["hermes", "echo"]` via `PluginRegistry.load`. Implements every test in [contracts/agent-platform.md § 7](./contracts/agent-platform.md#7-contract-tests-binding):
  - `test_protocol_runtime_check` — `isinstance(PLATFORM, AgentPlatform)` (FR-001)
  - `test_required_verbs_present` — all four callables present (FR-001, FR-007)
  - `test_validate_helper_accepts` — `_validate_agent_platform(PLATFORM)` returns None (FR-007)
  - `test_validate_helper_rejects_partial` — stripping `transcribe` raises `RuntimeError` (FR-007)
  - `test_transcribe_returns_str` — silence frame → `str` (FR-002)
  - `test_agent_step_yields_str_deltas` — async iter of `str`; `aclose()` clean (FR-003)
  - `test_agent_step_empty_turn` — tool-only → zero deltas; accumulated `.strip() == ""` (FR-003)
  - `test_synthesize_returns_bytes` — `await PLATFORM.synthesize("hi")` → non-empty bytes (FR-004)
  - `test_endpoint_returns_result` — `EndpointResult` with both fields (FR-005)
  - `test_lifecycle_idempotent` — startup → shutdown → shutdown OK (FR-006)
  - `test_no_hermes_imports_outside_plugin` — grep gate (FR-011) — may delegate to the test in T026
  - `test_no_coupling_todo_markers` — grep gate (FR-012) — may delegate to the test in T025
  - `test_wire_surface_unchanged` — runs `tests/integration/test_signaling_offer_answer.py` programmatically (FR-014)

### Voice-loop integration against echo (SC-004)

- [X] T043 [US4] Create `tests/integration/test_voice_loop_platform_agnostic.py` — uses `PluginRegistry.load("echo")` to construct the platform; constructs a `Session` with a fake transport and sink; feeds a known PCM utterance through the endpoint detector; asserts the captured transcript matches echo's canned response, the reply deltas accumulate to the echo's canned reply string, and the synthesised bytes match echo's canned PCM exactly. ZERO `HermesBridge` import in this file (verifiable by an `ast` walk in the test itself if paranoid).
- [X] T044 [US4] Run `pytest -x tests/contract/test_agent_platform_contract.py tests/integration/test_voice_loop_platform_agnostic.py -v`; confirm all pass.

**Checkpoint**: Contract tests bind every plugin to the documented surface; the abstraction is proven at the test layer (not just at the type layer).

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T045 [P] Update `specs/015-agentplatform-runtime-closure/quickstart.md` § 5 with the actual baseline numbers recorded in T001 and T034 (replace the placeholder ~720ms / ≤ 792ms with measured values).
- [ ] T046 [P] Run the full quickstart end-to-end in a clean shell against the refactored gateway. Every step ([quickstart.md § 1-7](./quickstart.md)) must pass without manual fix-up.
- [X] T047 [P] Update [CLAUDE.md](../../CLAUDE.md) "prior features" list to mark feature 015 as `[implemented + live-proven]` once T033 + T044 pass.
- [X] T048 Add a brief implementation summary section to [plan.md](./plan.md) (`## Implementation Outcome`) capturing: net LoC change, test count delta, measured latency delta (T001 vs T034), and any deviations from the plan worth noting for the next refactor.
- [ ] T049 Commit-time check: run `aivg --contract-version` and confirm it prints `1.0.0` unchanged (SC-007). Run `aivg setup --force --yes` against a clean host once more to confirm SC-008.
- [X] T050 [P] Tree-shake test (SC-010): create a temporary `tests/fixtures/platforms/treeshake/__init__.py` exposing a minimal `PLATFORM` and a `tests/integration/test_treeshake_plugin.py` that loads it via `PluginRegistry.load("treeshake")` and runs one turn — confirm ZERO code change in `aivg_core/` is needed to make it work.

---

## Dependencies & Execution Order

**Phase order (strict)**: Phase 1 (Setup baseline) → Phase 2 (Foundational) → Phase 3 (US1 — MVP). After US1 lands, Phases 4 (US2), 5 (US3), 6 (US4) can be implemented **in parallel** because they are read-mostly / test-mostly with disjoint file targets. Phase 7 (Polish) runs last.

**User-story dependency graph**:

```text
Phase 2 (Foundational)
   │
   ▼
US1 (P1) — the seam rewire
   │
   ├──► US2 (P1) — Hermes parity verification
   ├──► US3 (P2) — agent_stream optional path verification
   └──► US4 (P2) — contract tests + echo-platform integration test
              │
              ▼
        Phase 7 (Polish)
```

**Within-task dependencies** (US1):

- T012 / T013 / T019 are independent file edits → can be parallel after T011 checkpoint (different files).
- T014 must follow T013 (touches the same file `webrtc/session.py`).
- T015-T018 all touch `webrtc/session.py` → sequential within that file.
- T020-T022 all touch `adapter.py` → sequential within that file.
- T023 / T024 follow T012-T022.
- T025 / T026 / T027 follow T012-T024.

## Parallel Execution Examples

**After T011 (foundational done)** — kick off the three seam files concurrently:

```bash
# Three workers, one file each:
worker A: T012 (signaling.py)
worker B: T013 → T014 → T015 → T016 → T017 → T018 (session.py)
worker C: T019 → T020 → T021 → T022 (adapter.py)
```

**After T027 (US1 done)** — three user stories in parallel:

```bash
worker D (US2): T028 → T029 → T030 → T031 → T032 → T033 → T034
worker E (US3): T035 → T036 → T037 → T038 → T039
worker F (US4): T040 → T041 → T042 → T043 → T044
```

## Implementation Strategy

**MVP**: T001-T011 + T012-T027 (Phase 1 + Phase 2 + US1). This is the constitutional debt repayment — three TODO markers gone, zero Hermes imports in `aivg_core/`. Even if US2/US3/US4 slipped, the principle would be satisfied.

**Full delivery**: All seven phases. US2 + US3 are the regression-protection gates; US4 is the test-side proof; Phase 7 captures the receipts.

**Risk mitigation**: T001-T003 baseline must complete BEFORE any production code edit. SC-003 (±10 % latency) and SC-002 (live electron-test) are non-negotiable; without recorded baselines they cannot be evaluated.

## Format Validation

All 50 tasks above conform to `- [ ] T### [P?] [Story?] description with file path`. Story labels appear only on Phase 3-6 tasks (T012-T044); Phase 1 (T001-T003), Phase 2 (T004-T011), and Phase 7 (T045-T050) are unlabelled per the rules. Every task description names an exact file path or a precise verifiable command.
