---
description: "Task list for Make the Voice Turn Feel Snappy — instrument & reduce end-of-speech→first-word latency"
---

# Tasks: Make the Voice Turn Feel Snappy — Instrument & Reduce Voice-Turn Latency

**Input**: Design documents from `/specs/010-voice-turn-latency/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: New deterministic tests requested (spec SC-006 / plan):
`tests/unit/test_turnlatency.py` for the pure breakdown assembly +
a no-hardcoded-tuning-constant assertion. The existing suite (88) stays
100% green WITH NO EDITS (instrumentation is emit-only; the fake path is
unaffected — FR-009/SC-006).

**⚠️ PRODUCTION SAFETY**: redeploy is `🔒 LOCAL-MUTATING` — explicit
confirmation + prior backup; reuse/extend `deploy/deploy-local.sh`
(backup-first, idempotent, REVERSIBLE); the production ssh
`deploy-to-hermes.sh` stays untouched (FR-010).

**Organization**: US2 P1 measurable per-stage instrumentation · US1 P1
snappier reply (delivered + proven via US2's records) · US3 P2 no engine
rebuilt / config-driven not hardcoded / reversible. **US1 depends on US2**
(you cannot deliver or prove a reduction without the breakdown + a
recorded baseline — Principle V), so US2 is implemented first though both
are P1. Constitution: instrument + Hermes-config tuning only; no ASR/VAD/
agent/TTS engine reimplemented; zero hardcoded tuning constants (FR-011).

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Baseline: run `.venv/bin/python -m pytest -q` from repo root and record the existing suite (88) is green — regression baseline for FR-009/SC-006

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Pin the host seam/config; build the pure, locally-provable
breakdown core before wiring it.

**⚠️ CRITICAL**: Blocks US1, US2, US3

- [X] T002 Host re-verify (read-only, constitution V): in the running `~/.hermes/config.yaml` record actual `voice.silence_duration`, `voice.silence_threshold`, `stt.local.model`, the `satellite:` block shape, and confirm `SatelliteAdapterConfig` (`src/hermes_satellite_adapter/config.py`) exposes a path for an instrumentation knob; confirm `session.py` seams (`_collect_utterance` endpoint, `stt_transcribe` span, first `send_audio`) and `hermes_bridge.agent_stream` (first delta / first unit / first `tts_synthesize`); fix the agreed "typical short prompt" phrase; write all of it into `specs/010-voice-turn-latency/research.md` "Residual"
- [X] T003 Create `src/hermes_satellite_adapter/turnlatency.py` — pure, stdlib-only: given recorded stage instants (any may be absent) produce an ordered `LatencyBreakdown` over the canonical sequence (data-model.md) whose present stage durations sum to the end-to-end span within a small tolerance and which exposes the single dominant stage; never raise/hang on missing/out-of-order/duplicate instants (contracts L2/L3, FR-008)

**Checkpoint**: Host values/seams pinned; pure breakdown core exists
(unwired); nothing deployed

---

## Phase 3: User Story 2 - The latency is measurable per stage (Priority: P1)

**Goal**: Every turn emits one coherent per-stage breakdown via the
existing `LogSink`; a baseline is capturable. (Implemented before US1 —
US1's success is measured with this.)

**Independent Test**: `test_turnlatency.py` green + existing 88 green
(no edits); a live turn emits a breakdown whose stages sum to the total.

- [X] T004 [P] [US2] Create `tests/unit/test_turnlatency.py`: ordered breakdown over the canonical sequence; present stages sum to end-to-end within tolerance; dominant stage identified; missing / interrupted / error / empty-turn / duplicate-instant inputs handled (no raise/hang) — contracts L2/L3, FR-008/SC-003
- [X] T005 [US2] Wire stage instants in `src/hermes_satellite_adapter/session.py`: stamp monotonic instants at the existing seams — endpoint_detected (`_collect_utterance` returns end_of_utterance; derive end_of_speech = that − `voice.silence_duration` read from config), stt_done (after `stt_transcribe`), first_audio_delivered (first `send_audio`); on turn completion (success/error/barge-in/empty) build the `LatencyBreakdown` via `turnlatency.py` and emit it as ONE consolidated record through the existing `self._log`/`LogSink` at "turn complete" — emit-only, no behaviour/content change (contracts L1/L3/L4, FR-001/FR-002/FR-007/FR-008)
- [X] T006 [US2] In `src/hermes_satellite_adapter/hermes_bridge.py` `agent_stream` (host-only), record the three instants only it sees — agent_first_output (first `stream_callback` delta), first_unit_ready (first assembled unit), first_audio_synth (first `tts_synthesize` return) — onto the in-scope `turn`; minimal touch, must NOT alter 008 streaming / 009 strip / barge-in logic (contracts L1/L8, FR-006)
- [X] T007 [US2] Read the instrumentation verbosity/enable knob from the EXISTING `satellite:` block via the existing `SatelliteAdapterConfig` in `src/hermes_satellite_adapter/config.py` (default ON, lightweight always produced); NO new config file/loader/secret store; no hardcoded format-only behaviour (contracts L7, FR-011/FR-012)
- [X] T008 [US2] Run `.venv/bin/python -m pytest -q`: `test_turnlatency.py` green AND existing suite (88) still 100% green WITHOUT test edits (FR-009/SC-006)

**Checkpoint**: Per-turn breakdown emitted & summable; baseline capturable;
no regression locally — ready to measure

---

## Phase 4: User Story 1 - The reply starts noticeably sooner (Priority: P1) 🎯 MVP outcome

**Goal**: Deliver a measured ≥40% cut in end-of-speech→first-word for the
agreed prompt via reversible Hermes-config defaults; prove with US2's
before/after.

**Independent Test**: recorded baseline → after ≥40% lower (≤2 s target),
before/after breakdown shows the improved stage(s); 008/009/barge-in/
multi-turn unaffected.

- [X] T009 [US1] Extend `deploy/deploy-local.sh` with an idempotent, backup-first, REVERSIBLE step that sets faster Hermes defaults in `~/.hermes/config.yaml` (e.g. `voice.silence_duration` ↓, `stt.local.model` medium→small/base) using the SAME awk/backup mechanism it already uses for the `streaming:` block; values are config (operator-overridable, backup-restorable) — NOT hardcoded in adapter code; production `deploy-to-hermes.sh` untouched (contracts L6/L7, FR-004/FR-010)
- [X] T010 [US1] Confirm no avoidable satellite-side wait blocks the first unit: review `session.py`/`hermes_bridge.agent_stream` so stage 4/5 stay overlapped (008 preserved) and nothing buffers before first_unit_ready beyond what is required; record findings (no engine change — FR-005/FR-006)
- [X] T011 [US1] Static self-review vs contracts L1–L8 + constitution I/IV/V: only `turnlatency.py`(new)/`session.py`/`hermes_bridge.py`/`config.py`/`deploy-local.sh` touched; no ASR/VAD/agent/TTS engine added; endpointing still Hermes's algorithm; every tuning value config-driven (no hardcoded constant); 008/009/barge-in/multi-turn paths intact

**Checkpoint**: Faster reversible defaults in place + scope clean; the
≥40% is delivered (host-proven in Phase 6)

---

## Phase 5: User Story 3 - Faster without rebuilding engines; reversible (Priority: P2)

**Goal**: Prove no engine rebuilt, zero hardcoded tuning, fully reversible.

**Independent Test**: review + a test show no hardcoded tuning constant;
restoring the backup returns prior latency; pre-existing platforms intact.

- [X] T012 [US3] Add to `tests/unit/test_turnlatency.py` an assertion that tuning values are sourced from config (Hermes config / `satellite:` block), not module-level hardcoded constants — e.g. monkeypatch a config value and assert the consumed value changes (SC-009/FR-011, contract L7)
- [X] T013 [US3] Re-run `.venv/bin/python -m pytest -q`: full suite green after the config-source test + any wiring (no regression — FR-009/SC-006)
- [X] T014 [US3] Run `deploy/deploy-local.sh --preflight` (read-only): host reachable, deps present, snapshot pre-existing platforms (script reused, FR-010)

**Checkpoint**: No-rebuild + no-hardcode + reversibility locked by
review/tests; ready for the gated redeploy

---

## Phase 6: Live validation — host-proof (Priority: P1/P2)

**Goal**: Prove the real, perceived snappier turn + before/after evidence
on the local gateway with a human; nothing else regresses.

**Independent Test**: localhost Electron client (`127.0.0.1:8643/8644`,
no ssh/LAN/tunnel), real spoken exchange, before/after on one prompt.

- [X] T015 [US2] Live BASELINE (FR-003/L5 — Principle V): on the current (pre-tuning) build ask the agreed typical short prompt ~3×; from `~/.hermes/logs/` read the per-turn breakdowns; record the median per-stage + end-to-end baseline numbers in `specs/010-voice-turn-latency/quickstart.md`
- [X] T016 [US3] 🔒 LOCAL-MUTATING Execute `deploy/deploy-local.sh --yes` (gated, backup-first, idempotent): apply the faster reversible defaults + vendor the instrumentation build → restart gateway → post-verify (plugin import/register, 0 pre-existing platforms removed, both :8643 & :8644 LISTENING)
- [X] T017 [US1] Live AFTER (SC-001/SC-002/SC-004): ask the SAME prompt ~3× on the tuned build; median end-of-speech→first-audible-word ≥40% below the T015 baseline (target ≤2 s); the before/after breakdown shows WHICH stage(s) improved; log both number sets in `quickstart.md`
- [X] T018 [US1] Live NO-REGRESSION (FR-006/SC-005): same session — a long-answer prompt still streams first sentence fast (008), a Markdown answer is still clean (009), talking over a reply still barges in fast, a follow-up still has prior context (multi-turn); all unaffected
- [ ] T019 [US3] (SKIPPED per user 2026-05-19 — backup f007local.20260519T160320Z available for manual revert) 🔒 LOCAL-MUTATING Reversibility drill (SC-008): restore the latest `~/.hermes/config.yaml.bak.*` + `hermes gateway restart`; confirm latency returns to the T015 baseline and pre-existing platforms == pre-state in < 5 min; then redeploy to leave faster defaults live (operator-confirmed)

**Checkpoint**: Measured ≥40% improvement with evidence; no regression;
reversibility re-proven

---

## Phase 7: Polish & Cross-Cutting

- [X] T020 [P] Confirm scope discipline: only `turnlatency.py`(new) + `session.py` + `hermes_bridge.py` + `config.py` + `deploy-local.sh` + new test changed; transport/streamasm/adapter/contracts/production-deploy untouched; existing suite green with NO edits (FR-009/FR-010)
- [X] T021 [P] Update `specs/010-voice-turn-latency/quickstart.md` + `research.md` with the recorded baseline/after numbers, the chosen prompt + final config values, and any host deviation with justifying evidence (constitution V / Governance); update memory ([[feature-007-superseded]] chain → note 010 instrumentation + latency win landed) and leave the host per operator choice

---

## Dependencies & Execution Order

- **Setup (T001)** → **Foundational (T002–T003)** = host pinned + pure core; BLOCKS all
- **US2 (T004–T008)** before **US1 (T009–T011)**: US1's success is measured by US2's breakdown + a baseline (Principle V) — both P1, US2 first by dependency
- T005 depends on T003 (uses `turnlatency.py`); T006 small bridge touch independent of T005 file-wise but same feature — sequence T005→T006
- **US3 (T012–T014)** after US1/US2 code (asserts no-hardcode on the wired result)
- **Phase 6 (T015–T019)**: needs a human at a mic; T015 baseline BEFORE T016 deploy; T017/T018 after; T019 last (🔒)
- **Polish (T020–T021)** last; T020 ∥ T021

## Parallel Opportunities

- T004 ∥ early T002/T003 reasoning (test authored against the pure module)
- T020 ∥ T021 (scope re-check vs doc/memory update — different files)
- Most tasks are sequential: one pure module feeding shared seams in
  `session.py`, then config/deploy, then host-proof.

## Implementation Strategy

**MVP = Setup + Foundational + US2 + US1**: pin host (T002), build the pure
`turnlatency.py` + its tests (T003/T004), wire emit-only instrumentation at
the existing seams (T005–T007), prove locally green no-edits (T008), then
deliver the reduction via reversible Hermes-config defaults in
`deploy-local.sh` (T009) with scope/no-engine review (T010/T011). US3
locks no-hardcode + reversibility (T012–T014). Phase 6 is the human
host-proof: record baseline → gated reversible redeploy → prove ≥40% with
before/after evidence → confirm 008/009/barge-in/multi-turn intact →
reversibility drill. Measurement-first, config-only tuning, fully
reversible, never regresses prior features.

## Notes

- 🔒 LOCAL-MUTATING: T016, T019 — explicit confirmation + backup; reuse/
  extend `deploy/deploy-local.sh` (backup-first, reversible — FR-010);
  production ssh `deploy-to-hermes.sh` NOT touched.
- Constitution: V embodied (instrument → baseline → evidence-based change →
  host-proof); I/IV (no engine reimplemented; endpointing stays Hermes's;
  reuse `LogSink`/`SatelliteAdapterConfig`/Hermes config/`deploy-local.sh`;
  no new loader/store; **zero hardcoded tuning constants** — FR-011/SC-009).
  II/III untouched; 008/009/barge-in/multi-turn no regression; existing
  suite green with no edits (FR-006/FR-009/SC-005/SC-006). No Complexity
  Tracking (one pure module + existing seams/loader/deploy).
- Follows the feature-009 live finding (slowness = endpoint silence wait +
  Whisper-medium STT) — now measured & scoped, not silently tuned.
