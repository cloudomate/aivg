---
description: "Task list for Deploy & Live-Test the Voice Adapter"
---

# Tasks: Deploy & Live-Test the Voice Adapter on the Hermes Gateway

**Input**: Design documents from `/specs/003-deploy-test-adapter/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Conformance test tasks ARE included — the deployment-procedure and
electron-client contracts enumerate them. They are operational checks
(shell/manual), not a code unit suite.

**⚠️ PRODUCTION SAFETY**: Every task that mutates the `ssh hermes` host is
tagged `🔒 HOST-MUTATING` and MUST NOT run without explicit operator
confirmation and a prior backup (FR-003/004/006). `rollback.sh` is the tested
undo.

**Organization**: by user story — US1 P1 deploy · US2 P1 live conversation ·
US3 P2 rollback · US4 P2 observe · US5 P3 redeploy.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Create repo scaffolding: `deploy/`, `deploy/plugin/`, `clients/electron-test/`
- [X] T002 [P] Read `plugins/platforms/irc/plugin.yaml` + `__init__.py` on the host (read-only) and copy their exact shape as the template for ours
- [X] T003 [P] Add `clients/electron-test/package.json` (Electron + minimal deps; no STT/TTS/agent libs — constitution I)

**Checkpoint**: Skeleton dirs + verified plugin template in hand

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The plugin shim + safe deploy/rollback machinery every host story
depends on. No host story runs until these exist and are dry-run validated.

**⚠️ CRITICAL**: Blocks US1/US3/US5

- [X] T004 Write `deploy/plugin/plugin.yaml` (`kind: platform`, name `satellite_webrtc`, label, version, description, author) mirroring `plugins/platforms/irc/plugin.yaml`
- [X] T005 Write `deploy/plugin/__init__.py`: import feature 001's `hermes_satellite_adapter` + `platform_registry.register(build_platform_entry())` (reuses 001 T044's verified `PlatformEntry`; no new adapter code)
- [X] T006 Implement `deploy/deploy-to-hermes.sh` per contracts/deployment-procedure.md: ordered steps 1–7, each host-mutating step gated on explicit confirmation; records `config_backup_ref` and the ordered mutation list (FR-003/004/006)
- [X] T007 Implement `deploy/rollback.sh` per contract: restore `config.yaml` backup byte-for-byte → remove plugin dir → restart → verify pre-existing platforms == captured pre-state; non-zero on mismatch (FR-005/SC-006)
- [X] T008 [P] Implement preflight + pre/post regression capture in `deploy/deploy-to-hermes.sh --preflight` (gateway reachable; aiortc/aiohttp/av import in host venv; snapshot pre-existing platform list) — read-only, no mutation
- [X] T009 [P] Dry-run validate both scripts locally (shellcheck/`bash -n`, mocked ssh) — no host contact

**Checkpoint**: Deploy/rollback machinery proven by dry-run; nothing on the host changed yet

---

## Phase 3: User Story 1 - Deploy without breaking the gateway (Priority: P1) 🎯 MVP

**Goal**: Adapter registered/enabled on the live gateway; pre-existing
functionality unchanged.

**Independent Test**: Adapter appears registered + endpoints respond AND a
pre-existing platform still works.

- [X] T010 [US1] Run `deploy/deploy-to-hermes.sh --preflight`; capture pre-existing platform list (read-only)
- [X] T011 [US1] 🔒 HOST-MUTATING Execute `deploy/deploy-to-hermes.sh` (operator confirms each step): backup config → vendor plugin → add `satellite:` block → restart gateway (FR-001/003/004)
- [X] T012 [US1] Post-verify: adapter registered (`/satellite/list` reachable via host) AND a pre-existing platform exercised unchanged (FR-002 / SC-005); record result; if regression → invoke rollback
- [X] T013 [US1] Conformance: confirm no deploy step ≥3 ran without a recorded confirmation, and the `config.yaml` backup is byte-identical to pre-state (FR-003/FR-004/SC-007)

**Checkpoint**: MVP — adapter live on the gateway, zero regression, fully reversible

---

## Phase 4: User Story 2 - Real spoken conversation from the Electron client (Priority: P1)

**Goal**: A person speaks in the Electron app and hears the real Hermes agent
reply through the deployed adapter.

**Independent Test**: One spoken exchange → audible agent reply via the real
configured providers; latency shown.

- [X] T014 [P] [US2] Electron `main.js`: tray/window, host config (SSH-forwarded 8643/8644), mic-permission flow
- [X] T015 [US2] Electron `renderer.js`: control WS register/heartbeat to `WS /satellite/ws` (always-on; constitution III)
- [X] T016 [US2] Electron `renderer.js`: `getUserMedia({echoCancellation:true,…})` + `RTCPeerConnection` offerer, **full ICE gather → POST /webrtc/offer**, apply answer; hidden `<audio>` playback (no SDP munging; `browser_aec3`)
- [X] T017 [US2] Electron UI: push-to-talk control, state (idle/listening/thinking/speaking), transcript/reply text, end-of-speech→reply latency readout (v1: no wake word)
- [ ] T018 [US2] Establish `ssh -N -L 8643:localhost:8643 -L 8644:localhost:8644 hermes`; connect the client; confirm it appears in `/satellite/list`
- [ ] T019 [US2] Live test: speak one utterance, hear the real agent reply; record pass/fail + measured latency (SC-001/SC-002 ≤1.5 s; FR-009 real providers, parity SC-004)
- [ ] T020 [US2] Barge-in test: talk over the reply → playback stops ≤300 ms, new turn handled; confirm agent audio does not loop back (AEC) (SC-003 / FR-010)

**Checkpoint**: Real end-to-end conversation validated against the live build — closes feature 001 T045

---

## Phase 5: User Story 3 - Reversible deploy with one-step rollback (Priority: P2)

**Goal**: Gateway restored exactly to pre-deployment state on demand.

**Independent Test**: After deploy, rollback → gateway byte-for-byte back to
pre-state in <5 min.

- [ ] T021 [US3] 🔒 HOST-MUTATING Execute `deploy/rollback.sh`; restore config backup, remove plugin dir, restart (FR-005)
- [ ] T022 [US3] Verify post-rollback: `config.yaml` byte-identical to backup, plugin dir gone, pre-existing platforms == captured pre-state, completed <5 min (SC-006)
- [ ] T023 [US3] Conformance: simulate a mid-deploy failure (e.g. abort after step 4) → assert restored-or-`ROLLBACK REQUIRED`, never silent partial (FR-006)

**Checkpoint**: Deploy proven safely undoable

---

## Phase 6: User Story 4 - Observe & validate the live session (Priority: P2)

**Goal**: Operator sees the client, live state, logs, and a recorded pass/fail.

**Independent Test**: During a test conversation the client + state + logs are
visible and a pass/fail+latency is recorded.

- [ ] T024 [US4] During a redeployed live session, capture `/satellite/list`, `/satellite/{id}/state`, and per-session logs; confirm state timeline observed (FR-011)
- [ ] T025 [US4] Record a `Test Result` (pass/fail, eos→reply ms, regression_check, notes, deploy_id) per data-model.md (FR-012 / SC-008)
- [ ] T026 [P] [US4] Optionally drive/validate the gateway config via feature 002's vendored `hermes-agent` skill; host-mutating skill steps stay confirmation-gated

**Checkpoint**: Live test is observable and auditable

---

## Phase 7: User Story 5 - Repeatable redeploy (Priority: P3)

**Goal**: Redeploy a changed adapter version with no manual cleanup.

**Independent Test**: Deploy → change code → redeploy → new version runs, no
stale state.

- [ ] T027 [US5] 🔒 HOST-MUTATING Make a trivial adapter change, re-run `deploy/deploy-to-hermes.sh`; confirm the running adapter is the new version
- [ ] T028 [US5] Verify no stale prior-version state remains (plugin dir replaced atomically; `satellite:` block idempotent) (FR-013)

**Checkpoint**: Iteration loop works

---

## Phase 8: Polish & Cross-Cutting

- [X] T029 [P] Document deploy/test/rollback in `clients/electron-test/README.md` and link from quickstart.md
- [X] T030 [P] Confirm repo-side: features 001/002 artifacts untouched; this feature added only `deploy/` + `clients/` + `specs/003-*`
- [ ] T031 🔒 HOST-MUTATING Final state: leave the gateway rolled back to pre-deployment unless the operator explicitly opts to keep the adapter deployed (default = clean host)
- [ ] T032 Run `quickstart.md` end-to-end once and confirm every listed check passed; archive the Test Result

---

## Dependencies & Execution Order

- **Setup (P1)** → **Foundational (P2)** builds + dry-runs the deploy/rollback machinery; BLOCKS host stories
- **US1 (P1)** deploy → enables **US2 (P1)** conversation, **US4 (P2)** observe, **US5 (P3)** redeploy
- **US3 (P2)** rollback is independently runnable after US1 (and is the safety net for all host stories)
- **Polish (P8)** last; T031 default-restores the host
- Within Foundational: T004/T005 (plugin) ∥ T006/T007 (scripts); T008/T009 before any real host run

## Parallel Opportunities

- T002 ∥ T003; T004/T005 ∥ T006/T007; T008 ∥ T009
- US2 client build (T014–T017) proceeds in parallel with US1 deploy (different artifacts)
- T029 ∥ T030

## Implementation Strategy

**MVP = Phase 1 + 2 + US1 + US2**: machinery built & dry-run, adapter deployed
safely with zero regression, and one real spoken conversation validated
end-to-end (this is the user's actual ask and closes feature 001 T045). US3
rollback should be exercised immediately after US1 to prove reversibility
before deeper testing. Default end state = host rolled back (T031).

## Notes

- 🔒 HOST-MUTATING tasks (T011, T021, T027, T031) require explicit operator
  confirmation at execution; never auto-run.
- All host runtime deps already present (Phase 0) — no host install.
- Constitution: I (no embedded intelligence in adapter/client),
  III (two connections in the Electron client), IV (plugin reuse),
  V (this IS the live verification; backup/confirm/rollback gate every change).
- Reversible by design: `rollback.sh` + delete `deploy/`,`clients/`.
