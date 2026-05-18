---
description: "Task list for Real WebRTC Media Transport (audio actually flows)"
---

# Tasks: Real WebRTC Media Transport (audio actually flows)

**Input**: Design documents from `/specs/005-aiortc-media-transport/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Conformance tests ARE included (contract enumerates them): the
locally-provable `PcmFramer` unit suite (the testable slice of FR-004/C1/C3)
+ feature 001's fake-transport suite MUST stay 100% green (FR-012/SC-008).
The real WebRTC media path is host-proven by the live spoken test
(constitution V — aiortc/av are not local test deps).

**⚠️ PRODUCTION SAFETY**: redeploy/rollback tasks are `🔒 HOST-MUTATING` —
explicit confirmation + prior backup required; reuse features 003/004's tested
`deploy/deploy-to-hermes.sh` + `rollback.sh` (no new mechanism, FR-009).

**Organization**: US1 P1 real audio both ways · US2 P1 barge-in on real path ·
US3 P2 reversible redeploy · US4 P2 live spoken test completes.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Baseline: run `.venv/bin/python -m pytest -q` and record feature 001's fake-transport suite is green (regression baseline for FR-012/SC-008)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The real media code every story depends on (US1/US2 verify it,
US3 redeploys it, US4 needs it live). Replaces the single `NotImplementedError`
stub.

**⚠️ CRITICAL**: Blocks US1, US2, US3, US4

- [X] T002 [P] Create `src/hermes_satellite_adapter/media.py` (stdlib only): `frame_bytes(sample_rate, ms, channels=1, width=2) -> int` and `PcmFramer(frame_bytes)` with `push(data: bytes) -> list[bytes]` (yield complete frames, buffer remainder) and `flush() -> Optional[bytes]` (zero-pad tail to one full frame, else None); reject odd/≤0 `frame_bytes`; NEVER return a partial frame; NO VAD/endpointing (constitution I) — data-model.md `PcmFramer`
- [X] T003 Replace the `aiortc_transport_factory` body in `src/hermes_satellite_adapter/signaling.py`: lazy-import aiortc/av; build answerer `RTCPeerConnection`, `setRemoteDescription(offer)`, attach the outbound audio track, `createAnswer`+`setLocalDescription`; if no receivable inbound audio track within a bounded wait → raise a clear `RuntimeError` (offer fails loudly, never a hanging transport); return `(pc.localDescription.sdp, AiortcTransport(...))` — contracts F1/F2/F3, research D6
- [X] T004 Add `class AiortcTransport` to `src/hermes_satellite_adapter/signaling.py` implementing `session.MediaTransport`: `receive()` (inbound track `recv()`→`av.AudioResampler` s16/mono/48k→`PcmFramer` 20 ms/1920 B frames; `None` on track end or pc failed/closed, no exception); `send_audio(pcm)` (`av.open(BytesIO)` decode any container/rate→48k mono s16→enqueue on outbound track; empty/undecodable/sentinel bytes logged+dropped, never raises); `stop_playback()` (drain outbound queue, emit silence, reusable next turn); `connection_state` (pass through `pc.connectionState`); `close()` (idempotent: stop tracks, cancel reader, `await pc.close()`, no orphaned tasks) — contracts C1–C8, data-model.md `AiortcTransport`
- [X] T005 Confirm scope: `session.py`, `hermes_bridge.py`, `adapter.py`, `management.py`, the feature-001 contracts, and `deploy/*` are byte-unchanged; only `signaling.py` (+ new `media.py`) touched (FR-003/FR-008/FR-012)

**Checkpoint**: Stub gone; real transport exists behind the unchanged
`MediaTransport` Protocol; nothing deployed yet

---

## Phase 3: User Story 1 - Caller speech reaches the agent and the reply is heard (Priority: P1) 🎯 MVP

**Goal**: Real audio in → transcription; agent reply → audible playback, behind
the unchanged Protocol with no conversation-logic change.

**Independent Test**: Locally-provable framing/format logic green + feature 001
fake suite still green; real flow proven on host (US4 runs the spoken proof).

- [X] T006 [P] [US1] New `tests/unit/test_media_framer.py`: exact framing at the 1920 B boundary; remainder carry-over across multiple `push()` calls; `flush()` zero-pads a partial tail to a full frame and returns None when empty; odd/≤0 `frame_bytes` rejected; assert no `push()` ever returns a partial frame (the locally-provable slice of FR-004 / contract C1/C3)
- [X] T007 [US1] Run full `.venv/bin/python -m pytest -q`: new `test_media_framer.py` passes AND feature 001's fake-transport suite still 100% green (FR-012 / SC-008) — proves `session.py` still drives the unchanged Protocol
- [X] T008 [US1] Static self-review against contract C1–C4/C6–C8 and constitution I: `AiortcTransport` does only decode/encode/buffer (no STT/TTS/agent/endpointing/VAD); inbound is s16 mono 48 kHz 20 ms frames matching `HermesV013Bridge` defaults so STT parity holds (SC-001) and existing server-side endpointing fires on real audio (FR-001)

**Checkpoint**: MVP — real media code complete & locally proven where provable;
host-proof deferred to US4 (needs the deployed adapter + a microphone)

---

## Phase 4: User Story 2 - Barge-in works over real audio (Priority: P1)

**Goal**: In-flight outbound audio stops promptly when the caller speaks; the
transport is left usable for the next turn — on the real path.

**Independent Test**: `stop_playback()` flush behaviour reasoned/covered by the
queue-drain unit + proven ≤300 ms on host (US4 step 4).

- [X] T009 [US2] Verify in `src/hermes_satellite_adapter/signaling.py` that `stop_playback()` is O(queue)-cheap (drain + flushed flag + continue silence), well within `session.BARGE_IN_DEADLINE_S` (0.3 s), and leaves the outbound track non-wedged for the next `send_audio` (contract C5, research D4, last edge case)
- [X] T010 [US2] Re-run `.venv/bin/python -m pytest -q`: full suite still green after the barge-in path is finalized (no regression to the unchanged conversation logic, FR-012/SC-008)

**Checkpoint**: Barge-in path complete on the real transport; ≤300 ms proven on
host in US4

---

## Phase 5: User Story 3 - Reversibly redeploy the media-complete adapter (Priority: P2)

**Goal**: The media-complete adapter is the running version; gated;
reversible; zero regression to pre-existing platforms.

**Independent Test**: After gated redeploy, both ports listen + 5 pre-existing
platforms intact; rollback restores prior state <5 min.

- [X] T011 [US3] Run `deploy/deploy-to-hermes.sh --preflight` (read-only): host reachable, aiortc/aiohttp/av present, snapshot pre-existing platforms (reused unchanged, FR-009)
- [X] T012 [US3] 🔒 HOST-MUTATING Execute `deploy/deploy-to-hermes.sh` (gated, backup-first; reuses features 003/004 path unchanged): rsync the media-complete package → restart → post-verify (no embedded speech engine, plugin import/register, 0 pre-existing platforms removed, both :8643 & :8644 LISTENING)
- [X] T013 [US3] Confirm on host: `ss -ltn` shows 8643 AND 8644 LISTEN; `curl /satellite/list` ok; the 5 pre-existing platforms intact (SC-007 / FR-010)
- [ ] T014 [US3] 🔒 HOST-MUTATING Rollback drill: run `deploy/rollback.sh`; verify config byte-identical to backup + plugin removed + pre-existing platforms == pre-state in <5 min (SC-007); then redeploy to leave the media-complete adapter live for US4 (operator-confirmed)

**Checkpoint**: Media-complete adapter deployed; reversibility re-proven; zero
regression

---

## Phase 6: User Story 4
> **US4 BLOCKED (external defect, not feature 005):** live testing on 2026-05-18 confirmed the media path works (offer→answer→WebRTC connected, real audio in, end-of-speech fired, reply produced). The end-to-end test is blocked by a *pre-existing* gap: the constitution-III control-plane WebSocket `WS /satellite/ws` (port 8643) was never implemented — only REST management exists; `GET /satellite/ws` → HTTP 405 → client reconnect-thrash. Needs a separate fix-forward feature (006-class), mirroring feature 004's `build_signaling_app` pattern. T015–T017/T020 cannot pass until then.
 - The end-to-end live spoken test finally completes (Priority: P2)

**Goal**: The human-driven spoken conversation blocked since feature 003
(T019/T020) and feature 004 (T014/T015) is performed and passes.

**Independent Test**: From the desktop client over the forwarded ports, a real
spoken exchange yields an intelligible agent reply within a conversational
delay, with provider parity.

- [ ] T015 [US4] `ssh -N -L 8643:localhost:8643 -L 8644:localhost:8644 hermes`; from `clients/electron-test` (`npm start`), push-to-talk a phrase → offer succeeds (no "not implemented"), gateway transcribes it, agent reply plays **audibly** (US1 / FR-007 / SC-005); reply onset ≤1.5 s (SC-003); transcription parity + intelligible reply (SC-001/SC-002)
- [ ] T016 [US4] Live barge-in: talk over a playing reply → playback stops ≤300 ms and the interruption becomes the next turn; response addresses it (US2 / SC-004)
- [ ] T017 [US4] Hold ≥3 alternating turns — audio intact both ways, no progressive desync/dropout (SC-006); then drop the call and re-offer → audio re-establishes with NO gateway restart (FR-006)

**Checkpoint**: Long-blocked end-to-end spoken conversation passes; voice path
complete

---

## Phase 7: Polish & Cross-Cutting

- [X] T018 [P] Confirm scope discipline once more: only `signaling.py` + new `media.py` + new `tests/unit/test_media_framer.py` changed; `session.py`/bridge/contract/`deploy/*` untouched (FR-008/FR-009/FR-012)
- [X] T019 [P] Update `specs/005-aiortc-media-transport/quickstart.md` if route/format wiring differed from plan; note any deviation with its justifying constraint (constitution V / Governance)
- [ ] T020 Run `quickstart.md` end-to-end; archive the live-test result; ensure the host is left per operator choice (media-complete adapter live, or rolled back)

---

## Dependencies & Execution Order

- **Setup (T001)** → **Foundational (T002–T005)** = the real media code; BLOCKS all
- **US1 (T006–T008)**: verifies the locally-provable slice; no host
- **US2 (T009–T010)**: barge-in path finalized; no host
- **US3 (T011–T014)**: redeploys it (needs US1/US2 green); 🔒 host-mutating
- **US4 (T015–T017)**: needs US3 deployed + a human at a mic; the long-blocked proof
- **Polish (T018–T020)** last
- T002 → T004 (`AiortcTransport.receive` uses `PcmFramer`); T003 ↔ T004 same file (author together); T011 before T012; T012 before T013/T014

## Parallel Opportunities

- T002 ∥ T006 (new `media.py` vs new test file — author together) ;
  T018 ∥ T019

## Implementation Strategy

**MVP = Setup + Foundational + US1**: the stub is gone, the real
`AiortcTransport` exists behind the unchanged `MediaTransport` Protocol, the
locally-provable framing/format logic is tested, and the feature-001 fake
suite is still green. US2 finalizes barge-in. US3 makes it live (gated,
reversible via the existing `deploy/rollback.sh`). US4 is the long-blocked
human-driven spoken proof. Smallest possible change at the exact stub site;
fully reversible.

## Notes

- 🔒 HOST-MUTATING: T012, T014 — explicit confirmation + backup; reuse features
  003/004's gated scripts unchanged (FR-009), do not hand-edit the host.
- Constitution: I reinforced (transport is pure audio plumbing; `PcmFramer`
  is NOT a VAD; STT/TTS/agent/endpointing stay behind `HermesBridge`); V
  reinforced (locally-provable logic unit-tested, real WebRTC path honestly
  host-proven, deploy verified before relied on). II/III/IV preserved;
  `session.py` + contract + deploy scripts unchanged (FR-003/FR-008/FR-009/FR-012).
- The live spoken exchange (feature 003 T019/T020) still needs a human at a
  microphone; this feature removes the final technical blocker.
