---
description: "Task list for Agent Text-Delta Streaming Seam (speak while the agent composes — via the cli.py AIAgent delta pattern)"
---

# Tasks: Stream the Spoken Answer via the Agent Text-Delta Seam

**Input**: Design documents from `/specs/008-agent-delta-streaming/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Conformance tests are **reused from feature 007 unchanged**
(FR-011): `tests/unit/test_streamasm.py` (the `IncrementalUnitAssembler`
A1–A5 + retraction suite) stays green WITH NO EDITS, and feature 001's
fake-transport suite stays 100% green WITH NO EDITS (fake bridge has no
`agent_stream` → feature-006 fallback == SC-007). End-to-end streaming,
barge-in-aborts-generation, mid-stream failure, multi-turn continuity, and
the exact host `AIAgent`/`run_conversation`/`interrupt` entrypoints are
host-proven / host-verified (constitution V — not locally exercisable).

**⚠️ PRODUCTION SAFETY**: redeploy is `🔒 LOCAL-MUTATING` — explicit
confirmation + prior backup; reuse `deploy/deploy-local.sh` unchanged; the
production ssh `deploy-to-hermes.sh` stays untouched (FR-010).

**Organization**: US1 P1 answer begins while the agent composes · US2 P1
barge-in aborts generation · US3 P2 reversible local redeploy.
**Supersedes feature 007**: draft-streaming hook proven unreachable for the
LOCAL/voice path; this delivers the goal via the Hermes `AIAgent` text-delta
seam (cli.py pattern). 007's `streamasm.py` + tests reused unchanged.
**Analyze remediation folded in**: M1 (multi-turn continuity FR-012 →
T003 wiring + T020 live check).

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Baseline: run `.venv/bin/python -m pytest -q` and record feature 007's `tests/unit/test_streamasm.py` AND feature 001's fake-transport suite are green (regression baseline for FR-009/FR-011/SC-007)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Verified host agent-delta API + the streaming code every story depends on.

**⚠️ CRITICAL**: Blocks US1, US2, US3

- [X] T002 Host-API verification (read-only, constitution V): from the running local host `~/.hermes/hermes-agent` capture the EXACT `from run_agent import AIAgent` constructor arg set for a voice turn (mirror `cli.py`'s `AIAgent(...)` — model/fallback_model/toolsets/`session_id`/`session_db`/`stream_delta_callback`), the `AIAgent.run_conversation(user_message, system_message=None, conversation_history=None, task_id=None, stream_callback=None, persist_user_message=None)` signature, `AIAgent.interrupt(message=None)` + `is_interrupted()`, how `cli.py` runs it in a worker thread, AND how session/conversation context is supplied (session_id + conversation_history) so multi-turn parity is possible (FR-012); attempt a minimal headless `AIAgent` construct + one `run_conversation` smoke to confirm no CLI/TTY-only assumptions (de-risks the central feasibility); record findings in `specs/008-agent-delta-streaming/research.md` "Residual" — same discipline as 003/005/007
- [X] T003 Rewrite `src/hermes_satellite_adapter/hermes_bridge.py` `HermesV013Bridge.agent_stream` (host-only, pragma: no cover) per T002: lazily `from run_agent import AIAgent`, construct it as `cli.py` does (model/toolsets/session from Hermes config — invent no provider/config; constitution IV), **pass the per-session `session_id` + prior `conversation_history` into `run_conversation` so multi-turn context is preserved at feature-006 parity (FR-012 — no memory regression)**, run `run_conversation(user_text, conversation_history=…, stream_callback=cb)` in a worker thread; `cb(delta)` → feature-007 `IncrementalUnitAssembler.push(delta)`; completed units → EXISTING `tts_synthesize` (Hermes Piper) → yield audio in order; on run completion `assembler.flush()` → speak remainder; persist the turn back into the session history so the NEXT turn sees it; if `AIAgent` import/construct fails, fall back to feature 006 exactly (FR-005) — contracts H1–H3/H5/H7, FR-012
- [X] T004 Extend barge-in (bridge/session seam) so an interruption calls `AIAgent.interrupt()` (per T002) on the in-flight agent IN ADDITION to feature 006's stop_playback + pipeline cancel + abandoning the unit queue — no orphan unit AND no orphan agent generation (contracts H4, research D5, FR-004)
- [X] T005 Mid-stream-failure path (contract H6 / FR-008): confirm/wire that an agent or TTS exception raised *after* streaming has begun propagates through the EXISTING feature-006 turn-level failure handling (perceptible turn failure, session returns to listening, no broken/zero-length audio, no hang) and leaves no orphaned assembler/unit/agent run — reuse the existing turn error surface, add no new handler (constitution I/IV); `hermes_bridge.py`/`session.py` glue only
- [X] T006 Remove the now-dead feature-007 draft-hook glue from `src/hermes_satellite_adapter/adapter.py` (`supports_draft_streaming`, `send_draft`, `send`→`feed_final`, `_satellite_request_interrupt`, and the `F007` INFO probes) — proven unreachable for this path; keep only what the FR-005 feature-006 fallback (`agent_turn`) still needs (incl. whatever supplies session_id/history for FR-012); remove the matching probes in `hermes_bridge.py`
- [X] T007 Confirm scope: `streamasm.py` + `tests/unit/test_streamasm.py`, `signaling.py`/`AiortcTransport`, `media.py`, `textseg.py`, `management.py`, the feature-001/005/006/007-assembler contracts, and `deploy/*` are behaviourally unchanged; only `hermes_bridge.py` + `adapter.py` (+ minimal `session.py` glue) touched; fake/non-streaming path == feature 006 (FR-009/FR-011)

**Checkpoint**: Host agent-delta API pinned (incl. session/history seam);
the bridge runs Hermes's `AIAgent` with a delta sink + continuity; dead 007
glue removed; fake path still feature-006-identical; nothing deployed yet

---

## Phase 3: User Story 1 - Answer begins before the agent has finished thinking (Priority: P1) 🎯 MVP

**Goal**: First speakable unit is spoken from the agent's live delta stream
without waiting for full composition; later units continue as the agent
produces them; prior-turn context is retained (FR-012).

**Independent Test**: reused `test_streamasm.py` green (no edits) + feature
001 fake suite still green (no edits); cadence + continuity host-proven in
Phase 6.

- [X] T008 [US1] Run feature 007's `tests/unit/test_streamasm.py` UNCHANGED and confirm it passes (the deterministic FR-002/FR-003 slice is reused verbatim — FR-011; do NOT add or edit assembler tests)
- [X] T009 [US1] Run full `.venv/bin/python -m pytest -q`: `test_streamasm.py` passes AND feature 001's fake-transport suite still 100% green WITHOUT test edits (FR-005 fallback keeps the fake/non-streaming path == feature 006 — FR-009/FR-011/SC-007)
- [X] T010 [US1] Static self-review vs contracts H1–H3/H6/H7 + constitution I/IV + FR-012: the bridge runs Hermes's own `AIAgent`/`run_conversation` (the cli.py entrypoint) with session_id + conversation_history threaded for multi-turn parity; reuses feature 006 segmentation/TTS/transport + 007 assembler; STT=`transcribe_audio`, TTS=Hermes Piper; no agent/STT/TTS engine reimplemented; `MediaTransport` contract + turn-state semantics untouched

**Checkpoint**: MVP — agent-delta consumption + multi-turn continuity complete
& locally proven where provable; cadence/continuity host-proof deferred to
Phase 6

---

## Phase 4: User Story 2 - Barge-in interrupts a still-generating answer (Priority: P1)

**Goal**: Interruption stops audio promptly, abandons not-yet-spoken/
not-yet-generated units, AND calls `AIAgent.interrupt()` so the agent stops.

**Independent Test**: cancel+interrupt path reasoned/covered locally; ≤300 ms
audio stop + ≤1 s generation stop host-proven in Phase 6.

- [X] T011 [US2] Verify the barge-in path: feature 006 teardown (stop_playback + pipeline cancel → assembler/units abandoned) PLUS `AIAgent.interrupt()` (T004) fires for the in-flight agent; confirm no code path (incl. the T005 mid-stream-failure path) can leave the agent run going after an interrupt; the worker thread is joined/abandoned cleanly (contracts H4, research D5, spec edge "barge-in while generating")
- [X] T012 [US2] Re-run `.venv/bin/python -m pytest -q`: full suite still green after the interrupt + failure paths are finalized (no regression to unchanged conversation logic — FR-009/SC-007)

**Checkpoint**: Barge-in cancels playback AND agent generation; ≤300 ms / ≤1 s
proven on host in Phase 6

---

## Phase 5: User Story 3 - Reversibly redeploy on the local Hermes install (Priority: P2)

**Goal**: Agent-delta-streaming adapter is the running local version; gated;
reversible; zero pre-existing-platform regression.

**Independent Test**: post-redeploy both ports listen + pre-existing
platforms intact; restoring the config backup returns prior state < 5 min.

- [X] T013 [US3] Run `deploy/deploy-local.sh --preflight` (read-only): local host reachable, deps present (aiortc/aiohttp/av), snapshot pre-existing platforms (script reused unchanged, FR-010)
- [X] T014 [US3] 🔒 LOCAL-MUTATING Execute `deploy/deploy-local.sh --yes` (gated, backup-first, idempotent): backup config → vendor the package → restart local gateway → post-verify (no embedded speech engine, plugin import/register, 0 pre-existing platforms removed, both :8643 & :8644 LISTENING)
- [X] T015 [US3] Confirm on local host: `lsof` shows 8643 AND 8644 LISTEN; `curl localhost:8643/satellite/list` ok; the 5 pre-existing platforms intact (SC-008 / FR-010); re-approve pairing if needed (`hermes pairing approve local <CODE>`)
- [ ] T016 [US3] 🔒 LOCAL-MUTATING Reversibility drill: restore the latest `~/.hermes/config.yaml.bak.f007local.*` backup + `hermes gateway restart`; verify config matches backup + pre-existing platforms == pre-state < 5 min (SC-008); then redeploy to leave streaming live for Phase 6 (operator-confirmed)

**Checkpoint**: Streaming adapter deployed locally; reversibility re-proven;
zero regression

---

## Phase 6: Live validation — US1 & US2 host-proof (Priority: P1)

**Goal**: The end-to-end streaming + barge-in-aborts-generation +
mid-stream-failure + multi-turn continuity that cannot be exercised locally
are proven on the local gateway with a human.

**Independent Test**: localhost Electron client (`127.0.0.1:8643/8644`, no
ssh/LAN/tunnel), real spoken exchange with a long-composition question.

- [ ] T017 [US1] Live (SC-001/SC-002/SC-003/SC-006): FIRST record the feature-006 time-to-first-word baseline for a ≥10 s-answer prompt (e.g. "tell me a 40 line story"); then on the 008 build ask the SAME prompt — first audible sentence within ~3 s (SC-001); time-to-first-word ≥60% faster than the recorded 006 baseline (SC-002); ≤1.5 s inter-sentence gaps while generating, coherent, no missing/dup sentences (SC-003/SC-006); confirm in `~/.hermes/logs/agent.log` the delta stream is open WHILE sentences already play (first TTS precedes `response ready time=Xs`); log both numbers in `specs/008-agent-delta-streaming/quickstart.md`
- [ ] T018 [US1] Live: a one-line answer + an empty/tool-only case — no latency/correctness regression vs feature 006; if a turn can't stream, behaviour == 006 (SC-005 / FR-005)
- [ ] T019 [US2] Live: while a still-generating answer is speaking, talk over it — audio stops ≤300 ms, zero not-yet-spoken sentences, and agent generation ceases ≤1 s (verify in `~/.hermes/logs/agent.log`: no further `chat_completion_stream`/turn lines for that turn after the interrupt) (SC-004 / FR-004)
- [ ] T020 [US1] Live multi-turn continuity (FR-012 — M1): ask a turn that establishes context (e.g. "my name is Yash, remember it"), then a follow-up that depends on it (e.g. "what's my name?") — the agent's streamed answer MUST correctly use the prior turn's context, at parity with feature 006 (no memory regression from the handle_message→direct-AIAgent switch); confirm `~/.hermes/logs/agent.log` shows the follow-up turn ran with non-empty conversation history for the same session
- [ ] T021 [US1] Live (FR-008 / contract H6): induce or observe an agent/speech failure mid-stream — the turn fails perceptibly (no hang, no broken/zero-length audio), session returns to listening, and `~/.hermes/logs/` shows no orphaned agent run after the failure; if not naturally inducible, record it as observed/handled via the existing turn error surface (T002/T005)

**Checkpoint**: Conversational time-to-first-word, clean mid-generation
interrupt, multi-turn continuity, and perceptible mid-stream failure proven
on the local gateway

---

## Phase 7: Polish & Cross-Cutting

- [ ] T022 [P] Confirm scope discipline once more: only `hermes_bridge.py` + `adapter.py` + minimal `session.py` changed; `streamasm.py` + `tests/unit/test_streamasm.py` reused with NO edits; transport/contract/`deploy/*` untouched (FR-009/FR-010/FR-011)
- [ ] T023 [P] Update `specs/008-agent-delta-streaming/quickstart.md` + research.md if the verified `AIAgent` construction args / session-history threading / threading model differed from plan; record deviations + the 006/008 TTFW numbers + the multi-turn-continuity result (FR-012) with the justifying evidence (constitution V / Governance)
- [ ] T024 Run `quickstart.md` end-to-end; archive the live-test result; update memory ([[feature-007-superseded]] → 008 proven/landed, incl. continuity); leave the host per operator choice (streaming live, or restored)

---

## Dependencies & Execution Order

- **Setup (T001)** → **Foundational (T002–T007)** = host agent-delta API + streaming code + continuity + dead-glue removal; BLOCKS all
- T002 (host-API verify, incl. session/history seam + headless smoke) BEFORE T003/T004/T005 (they implement against the verified `AIAgent` API)
- T003 implements FR-012 (session_id + conversation_history threaded); reviewed in T010, host-proven in T020
- T006 (remove dead 007 glue) after T003; reviewed in T007/T010
- **US1 local (T008–T010)**: reuse 007 assembler test unchanged; no host
- **US2 local (T011–T012)**: interrupt-path + failure-path correctness; no host
- **US3 (T013–T016)**: redeploys locally (needs US1/US2 green); 🔒 local-mutating
- **Phase 6 (T017–T021)**: needs US3 deployed + a human at a mic — host-proof (T017 needs the 006 TTFW baseline recorded first; T020 needs ≥2 turns)
- **Polish (T022–T024)** last
- T022 ∥ T023

## Parallel Opportunities

- T022 ∥ T023 (scope re-check vs doc update — different files)
- (No `[P]` on assembler/test: feature 007's `streamasm.py` + its suite are
  reused UNCHANGED — FR-011 — not re-authored.)

## Implementation Strategy

**MVP = Setup + Foundational + US1**: host `AIAgent` API pinned (T002,
incl. session/history seam + headless smoke), the bridge runs Hermes's
`AIAgent` with a delta callback + session/history threading feeding feature
007's assembler → feature 006's per-sentence Hermes-Piper TTS → WebRTC, dead
007 draft-hook glue removed, multi-turn context preserved at 006 parity
(FR-012), and the fake/non-streaming path is feature-006-identical (FR-005 →
fake + reused assembler suites green, no edits). US2 adds
barge-in-aborts-generation via `AIAgent.interrupt()`. US3 ships it locally
(gated/reversible). Phase 6 is the human host-proof of conversational
time-to-first-word (vs a recorded 006 baseline), mid-generation interrupt,
multi-turn continuity, and perceptible mid-stream failure. Additive over 006;
no transport/contract change; fully reversible; never worse than 006
(FR-005). Supersedes the dead feature-007 draft-hook path.

## Notes

- 🔒 LOCAL-MUTATING: T014, T016 — explicit confirmation + backup; reuse
  `deploy/deploy-local.sh` unchanged (FR-010); the production ssh
  `deploy-to-hermes.sh` is NOT touched. Do not hand-edit the host beyond the
  gated script + the documented config restore.
- Analyze finding closed: **M1** (multi-turn continuity) → spec **FR-012** +
  T002 (verify session/history seam) + T003 (thread session_id +
  conversation_history into `run_conversation`, persist turn back) + T010
  (review) + T020 (live 2-turn proof). M2 (AIAgent-construct feasibility) is
  folded into T002's headless construct/`run_conversation` smoke.
- Constitution: I/IV reinforced (run Hermes's OWN `AIAgent`/`run_conversation`
  + Hermes STT/TTS + its `interrupt()` — the exact cli.py/Discord-voice
  entrypoints; reuse 007 assembler, 006 pipeline, 005 transport); V
  reinforced (host API + session seam verified before coding T002; assembler
  reused with its proven suite; end-to-end + continuity + failure
  host-proven). II/III preserved; transport contract + turn semantics
  behaviourally unchanged (FR-009); reused assembler suite + fake suite
  green, no edits (FR-011/SC-007). Complexity Tracking (plan.md): runs the
  agent in-adapter via the Hermes-native voice entrypoint — required by the
  binding goal, sanctioned by constitution IV, still "consume, don't rebuild".
- The ElevenLabs/local-speaker `tools.tts_tool.stream_tts_to_speaker` is
  deliberately NOT used (provider-locked, local-speaker only); only the
  agent-delta seam from the cli.py pattern is adopted (research D3).
- TTS text normalization (emoji/markdown) and STT model choice remain OUT OF
  SCOPE; this feature changes only reply sourcing/timing.
