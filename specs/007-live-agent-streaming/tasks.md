---
description: "Task list for End-to-End Streaming Conversation (speak while the agent is still thinking)"
---

# Tasks: End-to-End Streaming Conversation (speak while the agent is still thinking)

**Input**: Design documents from `/specs/007-live-agent-streaming/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Conformance tests ARE included (contract enumerates them): the
locally-provable `IncrementalUnitAssembler` unit suite (FR-001/FR-003 slice,
incl. the retraction/immutable-prefix invariant) + feature 001's fake-transport
suite MUST stay 100% green **with no test edits** (FR-005 fallback keeps the
fake/non-streaming path == feature 006 — SC-007). End-to-end streaming,
barge-in-cancels-generation, mid-stream-failure, and the exact host
draft-stream/interrupt APIs are host-proven / host-verified (constitution V —
not locally exercisable).

**⚠️ PRODUCTION SAFETY**: redeploy/rollback are `🔒 HOST-MUTATING` — explicit
confirmation + prior backup; reuse features 003/004 scripts unchanged (FR-010).
Deploy-gate quirk: feed confirmation via `yes yes | deploy/...`.

**Organization**: US1 P1 answer begins while agent still composing · US2 P1
barge-in cancels generation · US3 P2 reversible redeploy.
**Analyze remediation folded in**: C1 (FR-008/H6 mid-stream-failure
verification → T006/T020), U1 (assembler retraction/immutable-prefix invariant
→ T003/T008), O1 (record feature-006 TTFW baseline before the 60% claim →
T017).

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [ ] T001 Baseline: run `.venv/bin/python -m pytest -q` and record feature 001's fake-transport suite is green (regression baseline for FR-009/SC-007)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Verified host API + the streaming code every story depends on.

**⚠️ CRITICAL**: Blocks US1, US2, US3

- [ ] T002 Host-API verification (read-only, constitution V): from the running host `~/.hermes/hermes-agent/gateway/platforms/base.py` capture the EXACT `supports_draft_streaming` partner draft-update method name/signature + `edit_message(..., finalize=)` signature, the Hermes interrupt entrypoint for an in-flight turn, AND the existing turn-level error/failure surface for a mid-turn agent/TTS exception (resolves research D1/D3 residuals + the H6 reuse path before coding); record findings in `specs/007-live-agent-streaming/research.md` "Residual" section — same discipline as features 003/005
- [ ] T003 [P] Create `src/hermes_satellite_adapter/streamasm.py` (stdlib only): `IncrementalUnitAssembler` with `push(draft: str) -> list[str]` (emit only newly-complete speakable units via `textseg.iter_sentences` on the stable prefix; cumulative input never re-emits; **already-emitted prefix is immutable — a later shorter/divergent draft never un-says or re-emits an already-returned unit (spec edge "agent revises/retracts emitted text"; U1)**; buffer the incomplete tail) and `flush() -> list[str]` (remainder; idempotent; empty → []); preserve order, lose no finalized non-whitespace text; pure/deterministic, NO engine (constitution I) — data-model.md, contracts A1–A5
- [ ] T004 Modify `src/hermes_satellite_adapter/adapter.py` `_SatellitePlatformAdapter` (host-only, pragma: no cover) per T002 findings: `supports_draft_streaming() -> True`; implement the draft-update + `edit_message(..., finalize=True)` partner method to feed each update to an `IncrementalUnitAssembler`; completed units drive the EXISTING feature-006 per-unit Hermes TTS + transport playback; on finalize/done flush remaining; if the hook is not exercised for a turn, resolve the reply exactly as feature 006 (FR-005) — contracts H1–H3/H5/H7
- [ ] T005 Extend barge-in (adapter/session seam) so an interruption ALSO triggers the Hermes interrupt for the in-flight turn (per T002 entrypoint) in addition to feature 006's stop_playback + pipeline cancel — no orphan unit AND no orphan agent generation (contracts H4, research D3, FR-004)
- [ ] T006 Mid-stream-failure path (C1, contract H6 / FR-008 / spec edge "agent or speech provider fails mid-stream"): confirm/wire that an agent or TTS exception raised *after* streaming has begun propagates through the EXISTING feature-006 turn-level failure handling (perceptible turn failure, session returns to listening, no broken/zero-length audio, no hang) and does NOT leave the assembler, an in-flight unit, or agent generation orphaned — reuse Hermes's turn error surface (T002), add no new engine/handler (constitution I/IV); `adapter.py`/`session.py` glue only
- [ ] T007 Confirm scope: `signaling.py`/`AiortcTransport`, `media.py`, `textseg.py`, `management.py`, the feature-001/005/006 contracts, and `deploy/*` are behaviourally unchanged; only `streamasm.py` (new), `adapter.py`, and minimal `hermes_bridge.py`/`session.py` glue touched; fake/non-streaming path == feature 006 (FR-009)

**Checkpoint**: Host API pinned (incl. mid-turn error surface); streaming-
consumption + failure path exist; fake path still feature-006-identical;
nothing deployed yet

---

## Phase 3: User Story 1 - Answer begins before the agent has finished thinking (Priority: P1) 🎯 MVP

**Goal**: First speakable unit is spoken from the live draft without waiting
for full composition; later units continue as the agent produces them.

**Independent Test**: `test_streamasm.py` green + feature 001 fake suite still
green (no edits); cadence host-proven in Phase 6.

- [ ] T008 [P] [US1] New `tests/unit/test_streamasm.py`: cumulative drafts emit each complete unit once (no dup); partial trailing sentence buffered (no half-sentence); `flush()` returns remainder and is idempotent; append/delta input equivalent to cumulative; **a later shorter/divergent draft never un-says or re-emits an already-returned unit (immutable-prefix / retraction case — U1)**; concatenated units+flush loses no finalized non-whitespace text and preserves order; empty/whitespace → [] (contracts A1–A5 / FR-001/FR-003)
- [ ] T009 [US1] Run full `.venv/bin/python -m pytest -q`: new `test_streamasm.py` passes AND feature 001's fake-transport suite still 100% green WITHOUT test edits (FR-005 fallback keeps the fake/non-streaming path == feature 006 — FR-009 / SC-007)
- [ ] T010 [US1] Static self-review vs contracts H1–H3/H6/H7 + constitution I/IV: the adapter only consumes Hermes's own draft-streaming hook + reuses feature 006's segmentation/TTS/transport; mid-stream failure uses Hermes's existing turn error surface (no new handler); no agent/STT/TTS engine embedded; `MediaTransport` contract + turn-state semantics untouched

**Checkpoint**: MVP — streaming-consumption complete & locally proven where
provable; cadence host-proof deferred to Phase 6

---

## Phase 4: User Story 2 - Barge-in interrupts a still-generating answer (Priority: P1)

**Goal**: Interruption stops audio promptly, abandons not-yet-spoken/
not-yet-generated units, AND stops Hermes generating the rest.

**Independent Test**: cancel+interrupt path reasoned/covered locally; ≤300 ms
audio stop + ≤1 s generation stop host-proven in Phase 6.

- [ ] T011 [US2] Verify the barge-in path: feature 006 teardown (stop_playback + pipeline cancel → assembler/units abandoned) PLUS the Hermes interrupt (T005) fires for the in-flight turn; confirm no code path (incl. the T006 mid-stream-failure path) can leave agent generation running after an interrupt (contracts H4, research D3, spec edge "barge-in while generating")
- [ ] T012 [US2] Re-run `.venv/bin/python -m pytest -q`: full suite still green after the interrupt + failure paths are finalized (no regression to unchanged conversation logic — FR-009/SC-007)

**Checkpoint**: Barge-in cancels playback AND generation; ≤300 ms / ≤1 s
proven on host in Phase 6

---

## Phase 5: User Story 3 - Reversibly redeploy end-to-end streaming (Priority: P2)

**Goal**: Streaming-from-generation adapter is the running version; gated;
reversible; zero pre-existing-platform regression.

**Independent Test**: post-redeploy both ports listen + 5 pre-existing
platforms intact; rollback restores prior state < 5 min.

- [ ] T013 [US3] Run `deploy/deploy-to-hermes.sh --preflight` (read-only): host reachable, deps present, snapshot pre-existing platforms (reused unchanged, FR-010)
- [ ] T014 [US3] 🔒 HOST-MUTATING Execute `yes yes | deploy/deploy-to-hermes.sh` (gated, backup-first; features 003/004 path unchanged): rsync the streaming package → ~2-min restart drain → post-verify (no embedded speech engine, plugin import/register, 0 pre-existing platforms removed, both :8643 & :8644 LISTENING)
- [ ] T015 [US3] Confirm on host: `ss -ltn` shows 8643 AND 8644 LISTEN; `curl /satellite/list` ok; the 5 pre-existing platforms intact (SC-008 / FR-010)
- [ ] T016 [US3] 🔒 HOST-MUTATING Rollback drill: `yes | deploy/rollback.sh`; verify config byte-identical to backup + plugin removed + pre-existing platforms == pre-state < 5 min (SC-008); then redeploy to leave streaming live for Phase 6 (operator-confirmed)

**Checkpoint**: Streaming adapter deployed; reversibility re-proven; zero
regression

---

## Phase 6: Live validation — US1 & US2 host-proof (Priority: P1)

**Goal**: The end-to-end streaming + barge-in-cancels-generation +
mid-stream-failure behaviour that cannot be exercised locally are proven on
the production gateway with a human.

**Independent Test**: LAN-direct Electron client (`192.168.4.140`), real
spoken exchange with a long-composition question.

- [ ] T017 [US1] Live (SC-001/SC-002/SC-003/SC-006): FIRST on the still-feature-006 build (or from the 006 live-test record) ask a ≥10 s-answer prompt and **record the feature-006 time-to-first-word baseline for that exact prompt (O1)**; then on the streaming build ask the SAME prompt — first audible sentence within ~3 s (SC-001); time-to-first-word ≥60% faster than the recorded 006 baseline (SC-002); ≤1.5 s inter-sentence gaps while generating, coherent, no missing/dup sentences (SC-003/SC-006); log both numbers in `specs/007-live-agent-streaming/quickstart.md`
- [ ] T018 [US1] Live: a one-line answer + an empty/tool-only case — no latency/correctness regression vs feature 006; if a turn doesn't stream, behaviour == 006 (SC-005 / FR-005)
- [ ] T019 [US2] Live: while a still-generating answer is speaking, talk over it — audio stops ≤300 ms, zero not-yet-spoken sentences, and agent generation ceases ≤1 s (verify in `~/.hermes/logs/gateway.log`: no further response/streaming lines for that turn after the interrupt) (SC-004 / FR-004)
- [ ] T020 [US1] Live (C1 / FR-008 / contract H6): induce or observe an agent/speech failure mid-stream (e.g. a provider error during a long answer) — the turn fails perceptibly (no hang, no broken/zero-length audio), session returns to listening, and `~/.hermes/logs/gateway.log` shows no orphaned generation continuing after the failure; if not naturally inducible, record it as observed/handled via the existing turn error surface (T002/T006)

**Checkpoint**: Conversational time-to-first-word, clean mid-generation
interrupt, and perceptible mid-stream failure proven on prod

---

## Phase 7: Polish & Cross-Cutting

- [ ] T021 [P] Confirm scope discipline once more: only `streamasm.py` + `adapter.py` + minimal `hermes_bridge.py`/`session.py` + new `tests/unit/test_streamasm.py` changed; transport/contract/`deploy/*` untouched (FR-009/FR-010)
- [ ] T022 [P] Update `specs/007-live-agent-streaming/quickstart.md` + research.md if the verified host API, mid-turn error surface, or wiring differed from plan; record deviations + the 006/007 TTFW numbers (O1) with the justifying evidence (constitution V / Governance)
- [ ] T023 Run `quickstart.md` end-to-end; archive the live-test result; leave the host per operator choice (streaming live, or rolled back)

---

## Dependencies & Execution Order

- **Setup (T001)** → **Foundational (T002–T007)** = host API + streaming + failure code; BLOCKS all
- T002 (host-API verify, incl. mid-turn error surface) BEFORE T004/T005/T006 (they implement against the verified API)
- T006 (mid-stream-failure path) depends on T002+T004; reviewed in T010, re-checked in T011
- **US1 local (T008–T010)**: verifies the provable slice incl. the U1 retraction invariant; no host
- **US2 local (T011–T012)**: interrupt-path + failure-path correctness; no host
- **US3 (T013–T016)**: redeploys it (needs US1/US2 green); 🔒 host-mutating
- **Phase 6 (T017–T020)**: needs US3 deployed + a human at a mic — host-proof (T017 needs the 006 TTFW baseline recorded first)
- **Polish (T021–T023)** last
- T003 ∥ T008 (new module vs its test — author together) ; T021 ∥ T022

## Parallel Opportunities

- T003 ∥ T008 (new `streamasm.py` vs its new test) ; T021 ∥ T022

## Implementation Strategy

**MVP = Setup + Foundational + US1**: host API + mid-turn error surface pinned
(T002), the adapter consumes Hermes's draft-streaming hook and feeds feature
006's pipeline, mid-stream failure reuses Hermes's turn error surface (T006),
the provable assembler slice — incl. the retraction/immutable-prefix invariant
(U1) — is unit-tested, and the fake/non-streaming path is feature-006-identical
(FR-005 → fake suite green, no edits). US2 adds barge-in-cancels-generation.
US3 ships it (gated/reversible). Phase 6 is the human host-proof of
conversational time-to-first-word (against a recorded 006 baseline — O1),
mid-generation interrupt, and perceptible mid-stream failure. Additive over
006; no transport/contract change; fully reversible; never worse than 006
(FR-005).

## Notes

- 🔒 HOST-MUTATING: T014, T016 — explicit confirmation + backup; reuse
  features 003/004 gated scripts unchanged (FR-010); deploy-gate quirk: feed
  `yes`. Do not hand-edit the host.
- Constitution: I/IV reinforced (consume Hermes's own streaming + interrupt +
  turn-error hooks; agent/TTS stay Hermes-owned; reuse 006 segmentation, 005
  transport); V reinforced (host API + error surface verified before coding
  T002; assembler unit-tested incl. retraction; end-to-end + failure
  host-proven). II/III preserved; transport contract + turn semantics
  behaviourally unchanged (FR-009); fake suite green, no edits (SC-007).
  Complexity Tracking (plan.md): touches the agent-consumption seam — required
  by the binding goal, still "consume, don't rebuild".
- Analyze findings closed: **C1** FR-008/H6 → T002 (error-surface recon) +
  T006 (wire/confirm) + T010 (review) + T020 (host-prove); **U1** retraction
  invariant → T003 (rule) + T008 (test); **O1** SC-002 baseline → T017 records
  the 006 TTFW before asserting the 60% delta + T022 logs it.
- TTS text normalization (emoji/markdown) and STT model choice remain OUT OF
  SCOPE (separate concerns); this feature changes only reply sourcing/timing.
