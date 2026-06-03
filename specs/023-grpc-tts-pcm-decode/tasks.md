---
description: "Task list for feature 023 — gRPC downstream TTS decode to canonical 48 kHz PCM"
---

# Tasks: gRPC downstream TTS decode to canonical 48 kHz PCM

**Input**: Design documents from `/specs/023-grpc-tts-pcm-decode/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED — the spec defines a per-story "Independent Test" and the
quickstart enumerates unit + integration + a live end-to-end gate. This is a
correctness bug fix, so tests are the primary proof and are written before the
implementation they cover.

**Organization**: Tasks grouped by user story. NOTE: this fix centers on one
method (`GrpcMediaAdapter.send_audio`) plus one shared helper, so the foundational
phase lands the shared decode engine and each user story is an
independently-testable behavior slice layered on `send_audio` (clean audio →
robustness → pacing/barge-in).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 / US2 / US3 (Setup, Foundational, Polish have no story label)
- All paths are repo-relative from `/Users/yashwant.singh/coderepo/aivg/`

## Path Conventions

Single Python project: source under `src/aivg_core/`, tests under `tests/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the neutral home for the shared decoder and reusable test
audio fixtures.

- [X] T001 Create the neutral audio package: `src/aivg_core/audio/__init__.py` (empty package marker) so the shared decoder has a transport-neutral home (per plan.md Structure Decision).
- [X] T002 [P] Add a reusable test-audio fixture helper at `tests/unit/_audio_fixtures.py` that synthesizes small **encoded containers** in memory for tests: a mono WAV at a **non-48 kHz** rate (e.g. 24 kHz sine), a stereo WAV, and a deliberately-corrupt/non-container byte blob. (Use the stdlib `wave` module and/or `av`; return `bytes`.)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Land the single canonical decode engine that every user story relies
on. This is the shared spine — `send_audio` and all three stories call it.

**⚠️ CRITICAL**: No user story work can begin until the helper exists.

- [X] T003 [P] Write failing unit tests for the shared decoder in `tests/unit/test_tts_decode.py`: a non-48 kHz mono WAV decodes to s16 mono 48 kHz with the expected sample count (duration preserved within tolerance); a stereo WAV is downmixed to mono; undecodable bytes return `b""`; empty input returns `b""`; the function never raises. Use `tests/unit/_audio_fixtures.py`.
- [X] T004 Implement `decode_tts_to_pcm48k(pcm: bytes) -> bytes` in `src/aivg_core/audio/tts_decode.py` using PyAV (in-process ffmpeg): `av.open(io.BytesIO(pcm))` + `av.AudioResampler(format="s16", layout="mono", rate=48000)`, decode frame-by-frame, concatenate the resampled s16 bytes, and return them. Return `b""` (never raise) on empty input or `av.open` failure; on a mid-clip decode error, return what was decoded so far. Mirrors `webrtc/signaling.py:send_audio`'s decode loop. Make T003 pass.

**Checkpoint**: One canonical, ffmpeg-backed decoder exists and is unit-proven.

---

## Phase 3: User Story 1 - Clean spoken replies on a gRPC satellite (Priority: P1) 🎯 MVP

**Goal**: `GrpcMediaAdapter.send_audio` decodes the TTS clip to real 48 kHz PCM and
enqueues 20 ms frames, so the existing 48→16 downsample (gateway) and 16→48
upsample (client) produce intelligible speech instead of noise.

**Independent Test**: Drive a full gRPC voice turn with a provider clip whose
native rate ≠ 48 kHz; the satellite receives intelligible audio at correct
pitch/duration (not noise).

### Tests for User Story 1 ⚠️ (write first, ensure they FAIL)

- [X] T005 [P] [US1] In `tests/unit/test_grpc_media_adapter.py`, **migrate** `test_outbound_pump_emits_audio_serverframe` to feed a decodable **container** (non-48 kHz WAV from `_audio_fixtures`) instead of raw `b"\x00\x01"*960` PCM, and assert an `AudioChunk` `ServerFrame` is emitted with the existing codec/seq expectations. (Raw PCM is no longer valid input — see US2.)
- [X] T006 [P] [US1] Add a unit test in `tests/unit/test_grpc_media_adapter.py` asserting decode correctness: feeding a known non-48 kHz tone container yields downstream `AudioChunk` PCM whose decoded content reconstructs the tone (correct dominant frequency / non-noise, duration within tolerance) — the regression guard for this bug.
- [X] T007 [US1] Extend `tests/integration/test_grpc_transport_basic.py` with a full voice turn whose synthesized reply is a non-48 kHz container, asserting the client-received audio is intelligible/correct-rate (not noise).

### Implementation for User Story 1

- [X] T008 [US1] Rewrite `GrpcMediaAdapter.send_audio` in `src/aivg_core/transports/grpc/media_adapter.py`: call `decode_tts_to_pcm48k(pcm)`, push the result through a `PcmFramer(1920)` (imported from `aivg_core.webrtc.media`; instantiate once in `__init__`), and `await self._out.put(frame)` for each 20 ms frame; flush the framer tail at clip end. Wrap the body so it never raises out of `send_audio`. Leave `run_outbound_pump`, `stop_playback`, `close`, `ui_event_sink` unchanged. Make T005–T007 pass.
- [X] T009 [US1] Update the `_out` queue docstring/comment in `media_adapter.py` so it accurately states the queue now holds real 48 kHz s16 mono PCM frames (the invariant is now true), referencing feature 023.

**Checkpoint**: gRPC satellites play clean speech for normal (non-48 kHz) replies — the MVP that fixes the reported bug.

---

## Phase 4: User Story 2 - Graceful handling of empty / undecodable clips (Priority: P2)

**Goal**: Empty payloads, sentinels (`b"__PROVIDERS_UNAVAILABLE__"`), and
undecodable bytes emit no audio and never crash the stream/session — WebRTC parity.

**Independent Test**: Send empty / sub-minimal / corrupt bytes over gRPC; each
emits zero `AudioChunk`s, raises nothing, and leaves the session usable.

### Tests for User Story 2 ⚠️ (write first, ensure they FAIL)

- [X] T010 [P] [US2] Add unit tests in `tests/unit/test_grpc_media_adapter.py`: `send_audio(b"")`, `send_audio(b"short")` (`< 16` bytes), and `send_audio(b"__PROVIDERS_UNAVAILABLE__")` each enqueue **no** frames to `_out` and the adapter stays usable (a subsequent valid container still produces an `AudioChunk`).
- [X] T011 [P] [US2] Add a unit test in `tests/unit/test_grpc_media_adapter.py`: `send_audio` of corrupt/non-container bytes (from `_audio_fixtures`) emits no `AudioChunk` and does not raise.

### Implementation for User Story 2

- [X] T012 [US2] In `GrpcMediaAdapter.send_audio` (`media_adapter.py`), add the explicit early return `if not pcm or len(pcm) < 16: return` before decoding (covers empty + sentinel), matching `webrtc/signaling.py`. The undecodable path is already covered by `decode_tts_to_pcm48k` returning `b""` (T004) → no frames enqueued; confirm via T010/T011 and add a non-blocking diagnostic log/emit on the drop for parity. Make T010–T011 pass.

**Checkpoint**: US1 + US2 — clean audio for real replies, safe no-ops for empty/sentinel/undecodable.

---

## Phase 5: User Story 3 - Barge-in and streaming pipelining still work (Priority: P3)

**Goal**: The decode change preserves real-time pacing, frame-level barge-in, and
multi-clip streaming with no clicks or unbounded memory.

**Independent Test**: Over gRPC, barge-in mid-reply stops playback promptly; a
streamed multi-sentence reply plays in full; bounded queues never exceed maxsize.

### Tests for User Story 3 ⚠️ (write first, ensure they FAIL)

- [X] T013 [P] [US3] Add a unit test in `tests/unit/test_grpc_media_adapter.py`: after `send_audio` of a multi-second container fills `_out`, `stop_playback()` drains queued frames so no further `AudioChunk`s flow (frame-level barge-in preserved).
- [X] T014 [P] [US3] Add a unit test asserting streaming continuity in `tests/unit/test_grpc_media_adapter.py`: two consecutive `send_audio` clips in one turn produce downstream PCM with no discontinuity/click at the seam (the pump's carried `_downsample_state` keeps it seamless).
- [X] T015 [P] [US3] Extend `tests/integration/test_grpc_backpressure.py` to confirm `_out` (and `_server`) never exceed their `maxsize` when a slow/stalled consumer is simulated while `send_audio` streams a long clip (no unbounded growth; FR-021 preserved).

### Implementation for User Story 3

- [X] T016 [US3] Confirm/finish the framing + bounded-enqueue path in `send_audio` (`media_adapter.py`): per-frame `await self._out.put(...)` provides backpressure → real-time pacing; verify `stop_playback` still drains `_out` and `close` still unwinds the pump. Apply only minimal tweaks needed to make T013–T015 pass (no behavior change to `run_outbound_pump`).

**Checkpoint**: All three stories pass independently; barge-in, streaming, and bounded memory verified.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Consolidate to prevent recurrence, document, and complete the
Principle V live proof.

- [~] T017 [P] (Consolidation) **DEFERRED.** Refactoring `webrtc/signaling.py:send_audio` onto the shared helper would change WebRTC from *streaming* decode (enqueue frames as it decodes) to decode-whole-clip-then-enqueue, adding first-frame latency to the proven WebRTC path. The helper was extracted from WebRTC's own logic so the two are equivalent today; a future streaming/generator variant of `decode_tts_to_pcm48k` can consolidate them without the latency regression. Marked optional/deferrable in the plan.
- [X] T018 [P] Update `CHANGELOG.md` (gateway) with the feature 023 fix entry (gRPC downstream TTS now decoded/resampled to 48 kHz; internal-only, no wire change).
- [X] T019 [P] Add a brief note to `specs/023-grpc-tts-pcm-decode/` (or an existing tracking doc) recording that the **esphome** transport (`transports/esphome/media_adapter.py`) shares the same "queue raw bytes" shape and is tracked as a separate follow-up (spec Out of Scope).
- [X] T020 Run the full gateway test suite: `pytest tests/unit/test_grpc_media_adapter.py tests/unit/test_tts_decode.py tests/integration/test_grpc_transport_basic.py tests/integration/test_grpc_backpressure.py -q` and confirm green.
- [ ] T021 Execute the **Principle V live end-to-end gate** from `quickstart.md`: a real gRPC satellite + a non-48 kHz TTS provider, confirming clean speech, WebRTC A/B parity, prompt barge-in, full streamed reply, and a safe empty/error turn. Record the proof per the Development Workflow quality gate.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — start immediately.
- **Foundational (Phase 2)**: depends on Setup (needs the `audio/` package + fixtures). **BLOCKS all user stories** (they call the helper).
- **User Stories (Phase 3–5)**: all depend on Foundational. US1 is the MVP and lands the `send_audio` rewrite; US2 and US3 layer guards/pacing onto that same method, so within this feature they are sequential by priority (US1 → US2 → US3) even though each is independently *testable*.
- **Polish (Phase 6)**: depends on the user stories being complete (T020/T021 validate everything; T017 consolidation after gRPC is proven).

### User Story Dependencies

- **US1 (P1)**: after Foundational. Delivers the core fix (MVP).
- **US2 (P2)**: after US1 (edits the same `send_audio`; adds the empty/sentinel short-circuit + tests). Independently testable.
- **US3 (P3)**: after US1 (verifies/finishes pacing & barge-in on the same method). Independently testable.

### Within Each User Story

- Tests are written first and must FAIL before the implementation task.
- Helper (Foundational) before `send_audio` rewrite (US1) before guards (US2) / pacing (US3).

### Parallel Opportunities

- T002 (fixtures) runs parallel to T001.
- T003 (helper tests) can be authored in parallel once T001/T002 exist.
- Within a story, all `[P]` test tasks (different assertions, same/new test files authored together) can be drafted in parallel; the single implementation task per story is sequential after its tests.
- Polish tasks T017/T018/T019 are independent files → parallel.

---

## Parallel Example: User Story 1

```bash
# Author US1 tests together (they share the fixtures, distinct assertions):
Task: "T005 migrate raw-PCM unit test to a container in tests/unit/test_grpc_media_adapter.py"
Task: "T006 add decode-correctness unit test in tests/unit/test_grpc_media_adapter.py"
Task: "T007 add non-48k full-turn integration test in tests/integration/test_grpc_transport_basic.py"
# Then implement:
Task: "T008 rewrite GrpcMediaAdapter.send_audio (decode → frame → enqueue)"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup → Phase 2 Foundational (the shared ffmpeg-backed decoder).
2. Phase 3 US1: rewrite `send_audio` + its tests.
3. **STOP and VALIDATE**: a non-48 kHz reply plays as clean speech over gRPC (the
   reported bug is fixed). Demo-able.

### Incremental Delivery

1. Setup + Foundational → canonical decoder ready.
2. US1 → clean audio (MVP) → validate.
3. US2 → empty/sentinel/undecodable safety → validate.
4. US3 → barge-in + streaming + bounded memory → validate.
5. Polish → WebRTC consolidation, docs, live Principle V gate.

---

## Notes

- The fix is internal-only: **no proto/wire change, no client change** (FR-008).
- "Reuse ffmpeg" = PyAV (`av.open` + `av.AudioResampler`), in-process — no
  hand-rolled codec/resampler, no `ffmpeg` subprocess (research.md Decision 1).
- The pre-existing unit test fed **raw PCM**; that encodes the bug's wrong
  assumption and is migrated to a real container in T005.
- `PcmFramer` (in `webrtc/media.py`) and the 48→16 `audioop.ratecv` downsample are
  reused unchanged.
- Commit after each task or logical group; stop at any checkpoint to validate a
  story independently.
