---
description: "Task list for feature 024 — negotiated downstream PCM sample rate (gRPC)"
---

# Tasks: Negotiated downstream PCM sample rate (gRPC)

**Input**: Design documents from `/specs/024-downstream-rate-negotiation/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED — the spec defines a per-story "Independent Test" and the
quickstart enumerates contract + unit + integration + a live gate. Tests precede
the implementation they cover.

**Organization**: By user story. This is a small **additive** change — the
implementation concentrates in the proto enum value + `codec.py` selection
(foundational, shared by all stories) + one conditional in the outbound pump
(US1). US2 (back-compat) and US3 (fallback) are largely verification slices on
that shared machinery, which is exactly the point: the new rate reuses the
existing codec negotiation.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no dependency on incomplete tasks)
- **[Story]**: US1 / US2 / US3 (Setup/Foundational/Polish have no story label)
- Paths are repo-relative from `/Users/yashwant.singh/coderepo/aivg/`

## Path Conventions

Single Python gateway: source under `src/aivg_core/` + `src/aivg_cli/`; canonical
contract under `proto/aivg/satellite/v1/`; tests under `tests/`.

---

## Phase 1: Setup (Contract change)

**Purpose**: Land the additive wire-contract value every story builds on.

- [X] T001 Add `CODEC_PCM_S16LE_48K = 3;` to the `Codec` enum in `proto/aivg/satellite/v1/audio.proto` (with a comment: raw int16 LE mono PCM @ 48 kHz, device-native, no resample). Additive only — do not renumber or change existing values.
- [X] T002 Regenerate the checked-in Python stubs: run `bash scripts/gen_proto.sh`; verify `from aivg_core.transports.grpc._generated import audio_pb2; audio_pb2.Codec.Value("CODEC_PCM_S16LE_48K") == 3`. Commit the regenerated `_generated/` files.

---

## Phase 2: Foundational (Selection engine — blocks all stories)

**Purpose**: Make the gateway able to *select* and *label* the 48 kHz codec. All
three stories depend on this.

**⚠️ CRITICAL**: No user story work begins until selection treats 48 kHz as a
first-class, always-producible codec.

- [X] T003 [P] Write a failing contract test in `tests/contract/test_grpc_contract.py`: assert `CODEC_PCM_S16LE_48K` exists in the generated `Codec` enum (value 3) alongside the existing values.
- [X] T004 [P] Write failing unit tests in `tests/unit/test_grpc_codec.py`: `select_downstream_codec([CODEC_PCM_S16LE_48K], ...)` returns 48 k (always producible); `encode(CODEC_PCM_S16LE_48K, pcm)` is a passthrough; the operator default name `"pcm48k"` maps to `CODEC_PCM_S16LE_48K`.
- [X] T005 Implement in `src/aivg_core/transports/grpc/codec.py`: add `CODEC_PCM_S16LE_48K` alias; mark it producible (gateway pipeline is native 48 kHz); make `encode()` a passthrough for it; add `"pcm48k" -> CODEC_PCM_S16LE_48K` to `_NAME_TO_CODEC`. No structural change to `select_downstream_codec` (best-first/first-producible already works). Make T003–T004 pass.

**Checkpoint**: the gateway can select + label 48 kHz; `select_downstream_codec` honors it best-first and still falls back to 16 kHz.

---

## Phase 3: User Story 1 - 48 kHz device gets full-band, resample-free playback (Priority: P1) 🎯 MVP

**Goal**: When 48 kHz PCM is negotiated, the gateway sends its native 48 kHz audio
with **no** 48→16 downsample (SC-001), preserving the full band (SC-002).

**Independent Test**: A turn advertising `[CODEC_PCM_S16LE_48K]` yields
`AudioChunk`s stamped 48 k whose payload is 48 kHz PCM reconstructing the source
full-band — no downsample on the gateway path.

### Tests for User Story 1 ⚠️ (write first, ensure they FAIL)

- [X] T006 [P] [US1] Unit test in `tests/unit/test_grpc_media_adapter.py`: a `GrpcMediaAdapter(downstream_codec=CODEC_PCM_S16LE_48K)` fed a known tone (via `send_audio` of a container, reusing feature-023 fixtures) emits `AudioChunk`s whose payload is **48 kHz** (1920 B / 20 ms framing; total ≈ 3× the 16 kHz byte count) and reconstructs the tone with its **full band** (content above ~8 kHz retained — the no-bottleneck guard).
- [X] T007 [US1] Integration test in `tests/integration/test_grpc_transport_basic.py`: a full turn whose `SessionHeader.downstream_codec_pref=[CODEC_PCM_S16LE_48K]` (synth returns a real container) → every `AudioChunk.codec == CODEC_PCM_S16LE_48K`, payload length implies 48 kHz, and `SPEAKING_STARTED` still rides the stream.

### Implementation for User Story 1

- [X] T008 [US1] In `src/aivg_core/transports/grpc/media_adapter.py` `run_outbound_pump`: make the 48 kHz→16 kHz `audioop.ratecv` downsample **conditional** — when `self._codec == CODEC_PCM_S16LE_48K`, pass the native 48 kHz `chunk` straight to `encode()`/payload (no resample); otherwise downsample 48→16 exactly as today. (Derive the downstream rate from the codec once in `__init__` if cleaner.) Make T006–T007 pass.

**Checkpoint**: 48 kHz-negotiated sessions get resample-free, full-band downstream audio — the MVP.

---

## Phase 4: User Story 2 - Existing 16 kHz devices are unaffected (Priority: P1)

**Goal**: The default/16 kHz path is byte-identical to pre-feature behavior; the
change is additive and back-compatible (FR-005/007, SC-004/006).

**Independent Test**: A turn advertising nothing or `[CODEC_PCM_S16LE_16K]`
receives 16 kHz PCM identical to today, with no errors.

### Tests for User Story 2 ⚠️ (write first, ensure they FAIL → then pass unchanged)

- [X] T009 [P] [US2] Unit test in `tests/unit/test_grpc_media_adapter.py`: with `downstream_codec=CODEC_PCM_S16LE_16K` (and with empty prefs → default), the emitted `AudioChunk` payload is **16 kHz** (640 B/20 ms downsampled) — byte-for-byte equal to the pre-feature pump output for the same input (the conditional's else-branch is unchanged).
- [X] T010 [P] [US2] Integration test in `tests/integration/test_grpc_transport_basic.py`: a turn advertising no downstream rate (and one advertising `[CODEC_PCM_S16LE_16K]`) yields `AudioChunk.codec == CODEC_PCM_S16LE_16K`. (Keep/extend the existing basic-turn assertions.)

### Implementation for User Story 2

- [X] T011 [US2] Confirm the T008 conditional's else-branch leaves the 16 kHz path untouched (no code beyond the branch) and that empty/unknown prefs still select 16 kHz; make T009–T010 pass. No new production code expected — if a diff is needed, it is a bug in T008.

**Checkpoint**: US1 + US2 — 48 kHz when asked, unchanged 16 kHz otherwise.

---

## Phase 5: User Story 3 - Graceful fallback when a rate can't be served (Priority: P2)

**Goal**: An unproducible/unknown advertised rate falls back to a producible rate
(16 kHz default), and every chunk is labeled with the rate actually sent
(FR-006/008, SC-005/007).

**Independent Test**: Advertise an unproducible/unknown codec → gateway serves
16 kHz, every `AudioChunk.codec` matches its payload rate.

### Tests for User Story 3 ⚠️ (write first)

- [X] T012 [P] [US3] Unit test in `tests/unit/test_grpc_codec.py`: `select_downstream_codec` over a best-first list returns the first **producible** codec; an unproducible/unknown-only list falls back to the configured default then `CODEC_PCM_S16LE_16K`; mixed `[<unproducible>, CODEC_PCM_S16LE_48K]` selects 48 k.
- [X] T013 [P] [US3] Test (unit on the adapter, or integration) asserting the **label invariant**: across a turn, every emitted `AudioChunk.codec` matches the actual payload rate (16 k payload ⇒ stamped 16 k; 48 k payload ⇒ stamped 48 k) — the device never has to assume (SC-007).

### Implementation for User Story 3

- [X] T014 [US3] Verify fallback + labeling are already satisfied by T005 (selection) + T008 (the pump stamps `self._codec`, which equals the selected/producible codec). Add only the minimal assertion/guard needed to make T012–T013 pass; no new fallback path expected.

**Checkpoint**: all three stories pass; negotiation is robust across mixed/unknown prefs.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T015 Bump `CONTRACT_VERSION` `"0.3.0"` → `"0.4.0"` in `src/aivg_cli/cli.py` (additive wire change; research Decision 4). **NOTE: this is the one knob flagged for maintainer confirmation — skip T015–T016 if no contract bump is wanted.**
- [X] T016 [P] Update the contract-version assertions to `0.4.0` in `tests/unit/test_cli_help_contract.py`, `tests/unit/test_cli_tagline.py`, and `tests/integration/test_install_from_built_wheel.py`.
- [X] T017 [P] If `src/aivg_core/config.py` enumerates/validates `transports.grpc.downstream_codec`, allow `"pcm48k"` as an operator default (FR-009). If it accepts free strings, no change — just confirm `"pcm48k"` flows to `select_downstream_codec`.
- [X] T018 [P] Add a `CHANGELOG.md` entry: additive `CODEC_PCM_S16LE_48K` downstream codec lets 48 kHz devices skip the 48→16→48 double-resample; contract 0.3.0 → 0.4.0; back-compatible.
- [X] T019 Run the gRPC + contract-version suites green: `pytest tests/contract/test_grpc_contract.py tests/unit/test_grpc_codec.py tests/unit/test_grpc_media_adapter.py tests/integration/test_grpc_transport_basic.py tests/integration/test_grpc_backpressure.py tests/unit/test_cli_help_contract.py tests/unit/test_cli_tagline.py -q`.
- [ ] T020 **Principle V live gate (48 kHz)** on `iva` (RPi5 + XVF3800, I2S-48 kHz): drive a turn advertising `[CODEC_PCM_S16LE_48K]`, capture the `AudioChunk`s, confirm they are 48 kHz with **zero** resamples on the path (SC-001), play them full-band through the XVF3800, and A/B against the 16 kHz path (48 k retains high-frequency content). Reuse the `specs/023-grpc-tts-pcm-decode/live_proof.py` harness with the 48 kHz preference.
- [ ] T021 [P] Record the **C++ SDK / rpi-pipewire adoption** as a tracked follow-on (out of scope here): add `Codec::PcmS16le48k` mapping + `downstream_pref = 48k` and skip the device-side upsample — reconciling with the in-flight `fix/cpp-grpc-48k-resample` branch. Note it in this spec dir.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: the proto value + regen — start immediately. Blocks everything (the enum must exist).
- **Foundational (Phase 2)**: selection/labeling in `codec.py` — depends on Setup. **Blocks all user stories.**
- **US1 (Phase 3)**: the pump conditional — depends on Foundational. The MVP; lands the only real behavior change.
- **US2 (Phase 4)**: back-compat verification — depends on US1 (it asserts US1's else-branch is unchanged).
- **US3 (Phase 5)**: fallback/label verification — depends on Foundational (selection); independent of US1's pump branch.
- **Polish (Phase 6)**: contract-version bump, config, changelog, suite run, live gate — after the stories.

### Within Each User Story

- Tests first (fail), then the implementation task.
- Foundational `codec.py` before the US1 pump conditional.

### Parallel Opportunities

- T003 ∥ T004 (different test files).
- Within a story, `[P]` test-authoring tasks run together; the single impl task follows.
- Polish T016/T017/T018/T021 are independent files → parallel.

---

## Parallel Example: Foundational + US1

```bash
# Foundational tests together:
Task: "T003 contract enum test in tests/contract/test_grpc_contract.py"
Task: "T004 codec selection tests in tests/unit/test_grpc_codec.py"
# Then implement selection:
Task: "T005 codec.py: 48k producible + encode passthrough + name map"
# US1 tests, then the one behavior change:
Task: "T006 media_adapter 48k full-band unit test"
Task: "T008 run_outbound_pump conditional passthrough"
```

---

## Implementation Strategy

### MVP (Setup + Foundational + US1)

1. T001–T002 (contract) → T003–T005 (selection) → T006–T008 (pump passthrough).
2. **STOP and VALIDATE**: a 48 kHz-advertising turn gets resample-free full-band audio.

### Incremental Delivery

1. Contract + selection → 48 kHz is selectable/labeled.
2. US1 → resample-free 48 kHz (MVP).
3. US2 → prove 16 kHz unchanged (back-compat).
4. US3 → prove robust fallback + labeling.
5. Polish → contract 0.4.0, config, changelog, live 48 kHz gate on `iva`.

---

## Notes

- **Additive**: proto3 open enum → old↔new interoperate at 16 kHz (compat matrix
  in `contracts/audio-codec-48k.md`).
- The whole feature reuses the existing `downstream_codec_pref` + `select_downstream_codec`
  + per-chunk `AudioChunk.codec` — the only real behavior change is **one
  conditional** in `run_outbound_pump` (T008).
- Client adoption (C++ SDK / rpi-pipewire advertising 48 kHz) is **out of scope**
  (T021 tracks it); the live gate (T020) can use a Python client until then.
- Contract-version bump (T015–T016) is the one decision flagged for confirmation.
