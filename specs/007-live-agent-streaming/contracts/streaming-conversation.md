# Contract: End-to-End Streaming Conversation

**Status**: authoritative for feature 007.
**Reused unchanged**: `session.MediaTransport` Protocol, `AiortcTransport`,
feature 006 `textseg`/`tts_stream` segmentation+pipeline, the turn/state
machine, signaling, control plane, models (FR-009). This feature makes the
reply *source* incremental and extends barge-in to cancel agent generation.

## Assembler contract — `streamasm.IncrementalUnitAssembler`

| # | Requirement | Spec ref |
|---|-------------|----------|
| A1 | `push(draft)` returns only newly-**complete** speakable units (textseg semantics on the stable prefix); a trailing incomplete sentence is buffered, never returned. | FR-003 |
| A2 | Cumulative drafts never re-emit already-returned text; append/delta input handled equivalently. | SC-006 |
| A3 | Order preserved; all-returned-units + `flush()` loses no finalized non-whitespace text, no reordering. | SC-006 |
| A4 | `flush()` returns the buffered remainder; idempotent (2nd call → `[]`); empty input anywhere → `[]`. | FR-007 |
| A5 | Pure/deterministic, stdlib only, no STT/TTS/agent/VAD. | const. I |

## Streaming-consumption contract — adapter/bridge (host-only)

| # | Requirement | Spec ref |
|---|-------------|----------|
| H1 | The adapter opts into Hermes's draft-streaming hook (`supports_draft_streaming → True`) and feeds each update to the assembler; completed units drive per-unit Hermes TTS + transport playback (feature 006 pipeline). | FR-001/FR-002 |
| H2 | The first speakable unit is spoken without waiting for the full reply; later units continue in order as the agent produces them. | FR-001/FR-002, SC-001/SC-002 |
| H3 | On `finalize`/done, remaining buffered units are spoken; the turn completes with unchanged bookkeeping. | FR-002 |
| H4 | Barge-in stops playback, abandons not-yet-spoken/not-yet-generated units, **and** triggers Hermes's interrupt so agent generation stops ≤1 s; no orphan unit or orphan generation. | FR-004, SC-004 |
| H5 | If the streaming hook is not exercised for a turn (incl. the fake bridge), behaviour is **exactly feature 006** — no error, no worse. | FR-005, SC-005/SC-007 |
| H6 | Agent/speech failure mid-stream surfaces as a perceptible turn failure (existing turn-level handling), not a hang. | FR-008 |
| H7 | Agent + TTS remain Hermes-owned; only Hermes's own streaming/interrupt hooks are consumed. | FR-006, const. I/IV |

## Conformance tests

**Locally provable (must be green in `.venv`; SC-007 unaffected):**

- `tests/unit/test_streamasm.py` — A1–A5 (cumulative no-dup, partial-token
  buffering, finalize flush + idempotence, coverage/order, empty).
- Feature 001 fake-transport suite **unchanged & green** — proves H5/FR-009
  (fake bridge takes the 006 fallback; turn semantics identical).

**Host-proven (constitution V — live spoken test, US1/US2 / quickstart):**

- H1–H4/H6: for a ≥10 s answer the first sentence is heard ≤3 s and ≥60%
  faster time-to-first-word than 006 (SC-001/SC-002); ≤1.5 s inter-sentence
  gaps while generating (SC-003); coherent, no missing/dup sentences
  (SC-006); barge-in mid-generation stops audio ≤300 ms and agent generation
  ≤1 s with zero orphans (SC-004); short/empty no regression (SC-005).

## Out of scope (unchanged)

WebRTC media transport/contract, signaling, control plane, models, the
turn/state machine semantics, feature 006 segmentation internals, Hermes
STT/agent/TTS engines, TTS text normalization (emoji/markdown), STT model
choice, and deploy/rollback scripts (reused as-is, FR-010).
