---
description: "Task list for Streaming Spoken Replies (sentence-by-sentence)"
---

# Tasks: Streaming Spoken Replies (sentence-by-sentence)

**Input**: Design documents from `/specs/006-streaming-tts/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Conformance tests ARE included (contract enumerates them): the
locally-provable `iter_sentences` unit suite (segmentation slice of FR-002)
+ feature 001's fake-transport suite MUST stay 100% green **with no test
edits** (single-chunk fallback keeps fake behaviour identical — FR-008/SC-006).
Streaming cadence + barge-in are host-proven by the live spoken test
(constitution V — not locally exercisable).

**⚠️ PRODUCTION SAFETY**: redeploy/rollback are `🔒 HOST-MUTATING` — explicit
confirmation + prior backup; reuse features 003/004 scripts unchanged (FR-009).
Deploy-gate quirk persists: feed confirmation via `yes yes | deploy/...`.

**Organization**: US1 P1 reply streams sentence-by-sentence · US2 P1 barge-in
intact mid-stream · US3 P2 reversible redeploy.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Baseline: run `.venv/bin/python -m pytest -q` and record feature 001's fake-transport suite is green (regression baseline for FR-008/SC-006)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The streaming code every story depends on (US1 verifies it, US2
exercises barge-in over it, US3 redeploys it).

**⚠️ CRITICAL**: Blocks US1, US2, US3

- [X] T002 [P] Create `src/hermes_satellite_adapter/textseg.py` (stdlib only): `iter_sentences(text: str) -> list[str]` — split on `.?!`/newline+whitespace; merge sub-`MIN_CHARS` units forward; never split inside a decimal or a short known abbreviation (Mr. Dr. e.g. etc. vs. U.S. …); hard-split a boundary-less run-on at `MAX_CHARS`; preserve all non-whitespace text in order; empty/whitespace → []; pure/deterministic, NO VAD/endpointing/agent (constitution I) — data-model.md "Speakable Unit", contracts S1–S7
- [X] T003 Add `tts_stream(self, text, *, ctx) -> AsyncIterator[bytes]` to `HermesV013Bridge` in `src/hermes_satellite_adapter/hermes_bridge.py`: `iter_sentences(text)` → bounded look-ahead producer task (depth 1–2) that calls the EXISTING `tts_synthesize` per unit, pushing audio to an `asyncio.Queue`; yield in order; a unit whose synth raises is logged + skipped (FR-007); on `GeneratorExit`/`CancelledError` cancel the producer + drain (FR-004); empty input yields nothing (FR-006) — contracts T1–T6, research D3/D4/D6
- [X] T004 Modify `_respond` in `src/hermes_satellite_adapter/session.py`: add module helper `_reply_audio(bridge, text, ctx)` that uses `bridge.tts_stream` if present else yields one `await bridge.tts_synthesize(text, ctx=ctx)`; replace the single synth+send with `async for audio in _reply_audio(...): await self._transport.send_audio(audio)`; keep state transitions + barge-in path unchanged so the fake bridge (no `tts_stream`) is byte-identical to today — contracts C1–C4, FR-008
- [X] T005 Confirm scope: `signaling.py`/`AiortcTransport`, `adapter.py`, `management.py`, `media.py`, the feature-001/005 contracts, and `deploy/*` are behaviourally unchanged; only `textseg.py` (new), `hermes_bridge.py`, `session.py` touched (FR-008)

**Checkpoint**: Streaming path exists behind the Hermes seam; fake bridge
still single-chunk; nothing deployed yet

---

## Phase 3: User Story 1 - Reply starts speaking almost immediately (Priority: P1) 🎯 MVP

**Goal**: Multi-sentence reply is segmented + pipelined so the first sentence
plays within ~1.5 s; later sentences continue smoothly.

**Independent Test**: `test_textseg.py` green + feature 001 fake suite still
green (no edits); cadence host-proven in Phase 6.

- [X] T006 [P] [US1] New `tests/unit/test_textseg.py`: boundary splits; sub-threshold fragment merge; decimal (`3.14`) + abbreviation (`e.g.`, `Mr.`) not split; boundary-less run-on hard-split at `MAX_CHARS`; concatenation loses no non-whitespace text and preserves order; empty/whitespace → [] (contracts S1–S7 / FR-002)
- [X] T007 [US1] Run full `.venv/bin/python -m pytest -q`: new `test_textseg.py` passes AND feature 001's fake-transport suite still 100% green WITHOUT test edits (proves the single-chunk fallback keeps turn/state semantics identical — FR-008 / SC-006)
- [X] T008 [US1] Static self-review vs contracts C1–C2/T1–T3 + constitution I: segmentation/pipelining is text+scheduling only; every unit's audio still comes from Hermes `tts_synthesize` (same provider/voice); `MediaTransport` contract + turn state untouched

**Checkpoint**: MVP — streaming code complete & locally proven where provable;
cadence host-proof deferred to Phase 6

---

## Phase 4: User Story 2 - Barge-in still works during a streaming reply (Priority: P1)

**Goal**: Interrupting a streamed reply stops audio promptly and abandons all
not-yet-played AND not-yet-synthesized units.

**Independent Test**: cancel-path reasoned/covered locally; ≤300 ms + zero
orphan sentences host-proven in Phase 6.

- [X] T009 [US2] Verify in `hermes_bridge.py`/`session.py` that pipeline cancel unwinds `_reply_audio`→`tts_stream` (generator `finally` cancels the producer + drains; no further `tts_synthesize`), and `stop_playback()` drops the in-flight unit — so no orphan unit can play after barge-in and the transport stays usable (contracts C3/T5, research D4, spec edge cases)
- [X] T010 [US2] Re-run `.venv/bin/python -m pytest -q`: full suite still green after the cancel/cleanup path is finalized (no regression to unchanged conversation logic — FR-008/SC-006)

**Checkpoint**: Barge-in path correct over the streamed reply; ≤300 ms proven
on host in Phase 6

---

## Phase 5: User Story 3 - Reversibly redeploy the streaming reply (Priority: P2)

**Goal**: Streaming adapter is the running version; gated; reversible; zero
pre-existing-platform regression.

**Independent Test**: post-redeploy both ports listen + 5 pre-existing
platforms intact; rollback restores prior state < 5 min.

- [X] T011 [US3] Run `deploy/deploy-to-hermes.sh --preflight` (read-only): host reachable, aiortc/aiohttp/av present, snapshot pre-existing platforms (reused unchanged, FR-009)
- [X] T012 [US3] 🔒 HOST-MUTATING Execute `yes yes | deploy/deploy-to-hermes.sh` (gated, backup-first; features 003/004 path unchanged): rsync the streaming package → ~2-min restart drain → post-verify (no embedded speech engine, plugin import/register, 0 pre-existing platforms removed, both :8643 & :8644 LISTENING)
- [X] T013 [US3] Confirm on host: `ss -ltn` shows 8643 AND 8644 LISTEN; `curl /satellite/list` ok; the 5 pre-existing platforms intact (SC-007 / FR-010)
- [ ] T014 [US3] 🔒 HOST-MUTATING Rollback drill: `yes | deploy/rollback.sh`; verify config byte-identical to backup + plugin removed + pre-existing platforms == pre-state < 5 min (SC-007); then redeploy to leave streaming live for Phase 6 (operator-confirmed)

**Checkpoint**: Streaming adapter deployed; reversibility re-proven; zero
regression

---

## Phase 6: Live validation — US1 & US2 host-proof (Priority: P1/P2)

**Goal**: The streaming cadence + barge-in that cannot be exercised locally
are proven on the production gateway with a human at a microphone.

**Independent Test**: LAN-direct Electron client (`192.168.4.140`), real
spoken multi-sentence exchange.

- [ ] T015 [US1] Live: ask a multi-sentence question — first audible words within ~1.5 s of reply-ready (SC-001); sentences follow with ≤1 s gaps, no overlap/garble (SC-002); a 5+-sentence reply intelligible end-to-end (SC-004)
- [ ] T016 [US1] Live: ask a one-line answer + an empty/tool-only case — no latency/correctness regression vs feature 005 (SC-005 / FR-006)
- [ ] T017 [US2] Live: while a streamed reply is speaking, talk over it — audio stops ≤300 ms, ZERO not-yet-played sentences spoken afterwards, interruption becomes the next turn (SC-003 / FR-004)

**Checkpoint**: Streaming spoken reply proven natural + interruptible on prod

---

## Phase 7: Polish & Cross-Cutting

- [X] T018 [P] Confirm scope discipline once more: only `textseg.py` + `hermes_bridge.py` + `session.py` + new `tests/unit/test_textseg.py` changed; transport/contract/`deploy/*` untouched (FR-008/FR-009)
- [X] T019 [P] Update `specs/006-streaming-tts/quickstart.md` if segmentation thresholds or wiring differed from plan; record any deviation with its justifying constraint (constitution V / Governance)
- [ ] T020 Run `quickstart.md` end-to-end; archive the live-test result; leave the host per operator choice (streaming live, or rolled back)

---

## Dependencies & Execution Order

- **Setup (T001)** → **Foundational (T002–T005)** = the streaming code; BLOCKS all
- **US1 local (T006–T008)**: verifies the provable slice; no host
- **US2 local (T009–T010)**: cancel/cleanup correctness; no host
- **US3 (T011–T014)**: redeploys it (needs US1/US2 green); 🔒 host-mutating
- **Phase 6 (T015–T017)**: needs US3 deployed + a human at a mic — host-proof of US1/US2
- **Polish (T018–T020)** last
- T002 → T003 (`tts_stream` uses `iter_sentences`) → T004 (`_respond` uses the stream); T002 ∥ T006 (new module vs new test — author together); T011 before T012; T012 before T013/T014

## Parallel Opportunities

- T002 ∥ T006 (new `textseg.py` vs its new test) ; T018 ∥ T019

## Implementation Strategy

**MVP = Setup + Foundational + US1**: the reply is segmented + pipelined
behind the Hermes seam, the provable segmentation slice is unit-tested, and
feature 001's fake suite is still green with no edits (single-chunk fallback).
US2 confirms barge-in cleanup over the stream. US3 ships it (gated/reversible
via the existing `deploy/rollback.sh`). Phase 6 is the human-driven host
proof of the conversational cadence + interruptibility. Smallest change at
the seam; no transport/contract change; fully reversible.

## Notes

- 🔒 HOST-MUTATING: T012, T014 — explicit confirmation + backup; reuse
  features 003/004 gated scripts unchanged (FR-009); deploy-gate quirk: feed
  `yes`. Do not hand-edit the host.
- Constitution: I reinforced (segmentation = text/scheduling orchestration;
  audio still 100% Hermes TTS; `textseg` is NOT a VAD); V reinforced
  (segmentation unit-tested; streaming cadence/barge-in honestly host-proven).
  II/III/IV preserved; transport contract + turn semantics behaviourally
  unchanged (FR-008); fake suite green with no edits (SC-006).
- TTS text normalization (emoji/markdown spoken aloud) is explicitly OUT OF
  SCOPE (user deferred it); this feature changes only timing/segmentation.
