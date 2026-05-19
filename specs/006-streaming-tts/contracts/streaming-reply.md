# Contract: Streaming Spoken Reply

**Status**: authoritative for feature 006.
**Reused unchanged**: `session.MediaTransport` Protocol, the turn/state
machine, signaling, control plane, models (FR-008). This feature only adds an
ordered, pipelined reply-audio path behind the existing Hermes seam.

## Segmentation contract — `textseg.iter_sentences(text) -> list[str]`

| # | Requirement | Spec ref |
|---|-------------|----------|
| S1 | Splits text into ordered speakable units on sentence boundaries (`.?!`/newline + whitespace/EOL). | FR-002 |
| S2 | Units shorter than the min threshold merge forward (no choppy one-word audio). | FR-002, SC-002 |
| S3 | Never splits inside a decimal or a short known abbreviation. | Edge: intelligible segmentation |
| S4 | A boundary-less run-on is hard-split at a max length so playback can start early. | Edge: run-on; FR-001 |
| S5 | No non-whitespace text is lost or reordered across the unit list. | FR-002, SC-004 |
| S6 | Empty/whitespace-only input → empty list. | FR-006 |
| S7 | Pure/deterministic, stdlib only, no VAD/endpointing/agent. | const. I |

## Streaming contract — `HermesBridge.tts_stream(text, *, ctx)`

| # | Requirement | Spec ref |
|---|-------------|----------|
| T1 | Yields audio chunks (`bytes`) for the units of `text`, **in order**. | FR-002 |
| T2 | Synthesis of later units overlaps playback of earlier ones (bounded look-ahead producer). | FR-003, SC-001/SC-002 |
| T3 | Each unit's audio is produced only via the existing Hermes `tts_synthesize` (same provider/voice). | FR-005, const. I/IV |
| T4 | A unit whose synthesis fails is skipped (logged); the rest of the reply continues. | FR-007 |
| T5 | On generator close/cancel: producer cancelled, queue drained, no further units synthesized or yielded. | FR-004 |
| T6 | Empty/tool-only reply yields nothing (turn returns to listening as today). | FR-006 |

## Consumption contract — `session._respond` / `_reply_audio`

| # | Requirement | Spec ref |
|---|-------------|----------|
| C1 | `_reply_audio` uses `bridge.tts_stream` when present, else yields one `tts_synthesize` (fake bridge → today's behaviour). | FR-008, SC-006 |
| C2 | `_respond` plays units via `await transport.send_audio(chunk)` per unit; turn/state transitions unchanged. | FR-008 |
| C3 | Barge-in cancels the reply pipeline → `_reply_audio`/`tts_stream` unwinds (T5) and `stop_playback()` drops in-flight audio; no orphan unit plays. | FR-004, SC-003 |
| C4 | Short/empty replies show no latency/correctness regression vs feature 005. | FR-006, SC-005 |

## Conformance tests

**Locally provable (must be green in `.venv`; SC-006 unaffected):**

- `tests/unit/test_textseg.py` — S1–S7 (boundaries, merge, decimal/abbrev
  guard, run-on cap, coverage/order, empty).
- Feature 001 fake-transport suite **unchanged and green** — proves C1/C2/
  FR-008 (the fake bridge has no `tts_stream` → single-chunk fallback →
  identical turn behaviour).

**Host-proven (constitution V — live spoken test, US1/US2 / quickstart):**

- T1–T6, C3: a multi-sentence reply begins ≤1.5 s and streams sentence by
  sentence (SC-001/SC-002/SC-004); barge-in mid-stream stops ≤300 ms with
  zero orphan sentences (SC-003); short/empty replies unaffected (SC-005).

## Out of scope (unchanged)

WebRTC media transport (`AiortcTransport`), signaling, control plane, models,
turn/state machine semantics, Hermes STT/agent integration, TTS text
normalization (emoji/markdown — explicitly deferred by the user), and the
deploy/rollback scripts (reused as-is, FR-009/FR-010).
