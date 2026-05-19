# Contract: Agent Text-Delta Streaming Seam

**Status**: authoritative for feature 008. Supersedes feature 007's
`streaming-conversation.md` H-contract (draft-hook), which is proven
unreachable for this path.
**Reused unchanged**: `session.MediaTransport` Protocol, `AiortcTransport`,
feature 007 `streamasm.IncrementalUnitAssembler` (+ its unit suite), feature
006 segmentation + per-unit synth/playback pipeline, the turn/state machine,
signaling, control plane, models (FR-009). This feature makes the reply
*source* the Hermes agent's own text-delta stream and extends barge-in to
abort agent generation.

## Assembler contract — `streamasm.IncrementalUnitAssembler` (reused, A1–A5)

Unchanged from feature 007 (FR-011). A1 only newly-complete units; partial
tail buffered. A2 cumulative never re-emits; append/delta equivalent. A3
order preserved, lossless. A4 `flush()` remainder, idempotent, empty→[]. A5
pure/deterministic stdlib, no engine. Proven by
`tests/unit/test_streamasm.py` (reused, **no edits**).

## Agent-delta-streaming contract — bridge/adapter (host-only)

| # | Requirement | Spec ref |
|---|-------------|----------|
| H1 | The bridge runs Hermes's own `AIAgent` (`from run_agent import AIAgent`, constructed as `cli.py` does) via `run_conversation(user_text, stream_callback=cb)`; `cb` receives text deltas as the agent generates. No agent loop reimplemented. | FR-001/FR-006 |
| H2 | Each delta feeds `IncrementalUnitAssembler.push`; the first completed unit is spoken via the existing Hermes per-unit TTS + transport pipeline **without waiting for the full reply**; later units continue in order as deltas arrive. | FR-002/FR-003, SC-001/SC-002 |
| H3 | On agent-run completion, `assembler.flush()` speaks the remaining buffered unit(s); the turn completes with unchanged bookkeeping. | FR-002 |
| H4 | Barge-in stops playback, abandons not-yet-spoken/not-yet-generated units, **and** calls `AIAgent.interrupt()` so generation stops ≤1 s; no orphan unit or orphan generation. | FR-004, SC-004 |
| H5 | If the agent-stream seam is unavailable for a turn (incl. the fake bridge / AIAgent import failure), behaviour is **exactly feature 006** — no error, no worse. | FR-005, SC-005/SC-007 |
| H6 | An agent or speech failure mid-stream surfaces as a perceptible turn failure via existing turn-level handling, not a hang. | FR-008 |
| H7 | Speech recognition stays `transcription_tools.transcribe_audio`; TTS stays Hermes `tts_tool`/Piper per unit; only Hermes-owned entrypoints are used (the same ones Hermes's CLI/Discord voice modes use). | FR-006, const. I/IV |

## Conformance tests

**Locally provable (must be green in `.venv`; SC-007 unaffected):**

- `tests/unit/test_streamasm.py` — A1–A5 + immutable-prefix/retraction.
  **Reused from feature 007 with NO edits** (FR-011).
- Feature 001 fake-transport suite **unchanged & green** — proves H5/FR-009
  (fake bridge has no `agent_stream` → 006 fallback; turn semantics
  identical; no test edits).

**Host-proven (constitution V — local live spoken test, US1/US2 /
quickstart):**

- H1–H4/H6: for a ≥10 s answer the first sentence is heard ≤3 s and ≥60%
  faster time-to-first-word than 006 on the same prompt (SC-001/SC-002, 006
  baseline recorded first); ≤1.5 s inter-sentence gaps (SC-003); coherent, no
  missing/dup sentences (SC-006); barge-in mid-generation stops audio ≤300 ms
  and agent generation ≤1 s with zero orphans (SC-004); short/empty no
  regression (SC-005).

## Out of scope (unchanged)

WebRTC media transport/contract, signaling, control plane, models, the
turn/state-machine semantics, feature 006 segmentation internals, Hermes
STT/agent/TTS engines, TTS text normalization (emoji/markdown), STT model
choice, the production ssh deploy script, and the ElevenLabs/local-speaker
`stream_tts_to_speaker` sink (we use Hermes Piper via the existing pipeline).
