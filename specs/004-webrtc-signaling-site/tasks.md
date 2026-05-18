---
description: "Task list for Serve the WebRTC Signaling Site & Redeploy"
---

# Tasks: Serve the WebRTC Signaling Site & Redeploy

**Input**: Design documents from `/specs/004-webrtc-signaling-site/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Conformance tests ARE included (contract enumerates them):
lifecycle/teardown/ready-gate units + both-ports post-deploy check. Feature
001's 34-test fake suite MUST stay green (FR-010).

**⚠️ PRODUCTION SAFETY**: redeploy/rollback tasks are `🔒 HOST-MUTATING` —
explicit confirmation + prior backup required; reuse feature 003's tested
`deploy/`+`rollback.sh` (no new mechanism).

**Organization**: US1 P1 serve signaling · US2 P1 reversible redeploy ·
US3 P2 unblock live test.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Baseline: run `.venv/bin/python -m pytest -q` and record feature 001's suite is green (regression baseline for FR-010)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The code fix every story depends on (US2 redeploys it, US3 needs
it live).

**⚠️ CRITICAL**: Blocks US1 verification, US2, US3

- [X] T002 Add `build_signaling_app(service)` to `src/hermes_satellite_adapter/signaling.py`: lazy `aiohttp`; routes `POST /webrtc/offer`→`handle_offer`, `POST /webrtc/candidate`→204, `GET /webrtc/status/{device_id}`→`status` (mirror `build_management_app`; constitution IV) — contracts/signaling-site-lifecycle.md
- [X] T003 Modify `src/hermes_satellite_adapter/adapter.py` `start()`: after the management site, build+start the signaling site on `cfg.webrtc_port`; append BOTH runners to `self._sites`; on signaling bind-failure tear down the management site and raise (FR-005) — never half-up
- [X] T004 Verify `stop()` cleans every runner in `self._sites` (both planes) — no orphaned listeners (FR-004)

**Checkpoint**: Adapter serves both planes or fails loudly; nothing deployed yet

---

## Phase 3: User Story 1 - Adapter serves WebRTC signaling (Priority: P1) 🎯 MVP

**Goal**: Both planes come up; offer→answer creates a session; half-up is a
hard failure.

**Independent Test**: Unit suite proves the lifecycle; 001 suite still green.

- [X] T005 [P] [US1] New `tests/unit/test_adapter_sites.py`: with an `aiohttp.web` shim, assert `build_signaling_app` exposes the 3 routes and they target `SignalingService.handle_offer/status`
- [X] T006 [P] [US1] `tests/unit/test_adapter_sites.py`: `start()` registers TWO runners (mgmt+signaling); `stop()` cleans both (FR-003/FR-004)
- [X] T007 [US1] `tests/unit/test_adapter_sites.py`: simulated signaling bind-failure ⇒ `start()` raises AND the management runner was cleaned (FR-005/SC-005) — proves no silent half-up recurrence
- [X] T008 [US1] Run full `.venv/bin/python -m pytest -q`: new tests pass AND feature 001's 34 tests still green (FR-010 / SC unchanged-logic)

**Checkpoint**: MVP — fix proven locally; control-up/signaling-down is now impossible silently

---

## Phase 4: User Story 2 - Reversibly redeploy the fix (Priority: P1)

**Goal**: The fixed adapter is the version running on the gateway; reversible;
zero regression.

**Independent Test**: After gated redeploy, both ports listen + pre-existing
platforms intact; rollback restores prior state.

- [X] T009 [US2] Extend `deploy/deploy-to-hermes.sh` `postverify()`: additionally assert BOTH `:8643` and `:8644` are LISTENING on the host (SC-001); fail→`ROLLBACK REQUIRED` if either missing (keep existing constitution-I + SC-005 checks)
- [X] T010 [US2] Run `deploy/deploy-to-hermes.sh --preflight` (read-only)
- [X] T011 [US2] 🔒 HOST-MUTATING Execute `deploy/deploy-to-hermes.sh` (gated, backup-first; reuses feature 003 path, FR-006): rsync fixed package → restart → extended post-verify
- [X] T012 [US2] Confirm on host: `ss -ltn` shows 8643 AND 8644 LISTEN; `curl /satellite/list` ok; 5 pre-existing platforms intact (SC-001/SC-003)
- [ ] T013 [US2] 🔒 HOST-MUTATING Rollback drill: run `deploy/rollback.sh`; verify config byte-identical to backup + plugin removed + pre-existing platforms == pre-state <5 min (SC-004); then redeploy to leave the fix live for US3 (operator-confirmed)

**Checkpoint**: Fixed adapter deployed; reversibility re-proven

---

## Phase 5: User Story 3 - Unblock the live conversation test (Priority: P2)

**Goal**: The Electron client's WebRTC offer connects (no signaling-port
failure), enabling feature 003 T018–T020.

**Independent Test**: From the forwarded ports, an offer to 8644 returns an
answer and a session appears.

- [ ] T014 [US3] `ssh -N -L 8643:localhost:8643 -L 8644:localhost:8644 hermes`; confirm a POST to `localhost:8644/webrtc/offer` is no longer connection-refused (SC-006)
- [ ] T015 [US3] Hand-off: with `clients/electron-test` (feature 003), the offer connects + session is created/visible in `/satellite/list`; the human-driven spoken exchange (feature 003 T019/T020) can now proceed

**Checkpoint**: Signaling blocker removed; feature 003 live test unblocked

---

## Phase 6: Polish & Cross-Cutting

- [ ] T016 [P] Update feature 001 `contracts/webrtc-signaling.md` note + this feature's quickstart if route wiring differs from plan
- [ ] T017 [P] Confirm scope discipline: only `signaling.py`, `adapter.py`, `deploy/deploy-to-hermes.sh`, and new test changed; `session.py`/bridge/contract untouched (FR-009/010)
- [ ] T018 Run `quickstart.md` end-to-end; archive result; ensure host left per operator choice (fix live for US3, or rolled back)

---

## Dependencies & Execution Order

- **Setup (T001)** → **Foundational (T002–T004)** = the code fix; BLOCKS all
- **US1 (T005–T008)**: verifies the fix locally — no host
- **US2 (T009–T013)**: redeploys it (needs US1 green); 🔒 host-mutating
- **US3 (T014–T015)**: needs US2 deployed; unblocks feature 003 live test
- **Polish (T016–T018)** last
- T002 → T003 (start uses the builder) → T004; T009 before T011

## Parallel Opportunities

- T005 ∥ T006 (same new file, different cases — author together) ; T016 ∥ T017

## Implementation Strategy

**MVP = Setup + Foundational + US1**: the fix exists and is proven locally
(both-plane lifecycle + ready-gate + 001 suite green). US2 makes it live
(gated, reversible); US3 unblocks the feature-003 spoken test. Smallest
possible change; fully reversible via the existing `deploy/rollback.sh`.

## Notes

- 🔒 HOST-MUTATING: T011, T013 — explicit confirmation + backup; reuse feature
  003's gated scripts (FR-006), do not hand-edit the host.
- Constitution: reinforces III (two separate plane sites; ready-gate forbids
  half-up) and V (both-ports verified post-deploy). I/IV preserved; conversation
  logic + satellite contract unchanged (FR-009/010).
- The live spoken exchange itself remains feature 003's scenario (needs a human
  at a mic); this feature only removes the signaling blocker.
