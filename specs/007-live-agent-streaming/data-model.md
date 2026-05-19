# Phase 1 Data Model: End-to-End Streaming Conversation

No persisted data, no new shared models. Features 001/005/006 entities are
reused behaviourally unchanged (FR-009). New constructs are runtime-only.

## Entity: `IncrementalUnitAssembler` (`streamasm.py`, new, stdlib)

Turns a sequence of streaming reply updates into ordered, complete speakable
units. Pure/deterministic, no engine (constitution I). Locally unit-tested.

| Member | Description |
|--------|-------------|
| `push(draft: str) -> list[str]` | accept the latest update (cumulative draft text, or an append delta — both handled); return any newly-**complete** speakable units not yet returned |
| `flush() -> list[str]` | finalize: return the buffered remainder as the last unit(s); idempotent (second call → `[]`) |
| internal `_spoken_len` | how much of the text has already been emitted as units |
| internal `_buf` | the not-yet-complete trailing text |

Rules:

- Segmentation reuses `textseg.iter_sentences` semantics on the **stable
  prefix** only; a trailing incomplete sentence is buffered, never spoken
  (FR-003 — no half-sentence audio).
- Cumulative input: `push` only emits units for text beyond `_spoken_len`;
  already-emitted text is never re-emitted (no duplicate sentences — SC-006).
- Append/delta input degenerates correctly (delta = cumulative minus prefix).
- Order preserved; concatenating all returned units + final flush loses no
  finalized non-whitespace text and never reorders it.
- Empty/whitespace updates → `[]`; `flush()` on empty → `[]`.
- Idempotent `flush()` (a late duplicate finalize is a no-op).

## Entity: Incremental Reply Source (adapter/bridge seam — host-only)

`_SatellitePlatformAdapter` (host-only, `pragma: no cover`):

| Aspect | Behaviour |
|--------|-----------|
| `supports_draft_streaming()` | returns `True` (opt into the Hermes hook) |
| draft-update method | each call → `assembler.push(text)` → completed units fed to the existing per-unit Hermes TTS + transport playback (feature 006 pipeline) |
| `edit_message(..., finalize=True)` / done | `assembler.flush()` → speak remaining units; turn reply considered complete |
| no streaming for this turn | fall back: resolve the reply exactly as feature 006 (single text → 006 `tts_stream`) — FR-005 |
| barge-in | feature-006 teardown **plus** Hermes interrupt for the in-flight turn so generation stops (FR-004) |

Exact host method names/signatures verified against the running
`gateway/platforms/base.py` at implement time (constitution V; residual list
in research.md).

## State / lifecycle (reused, unchanged)

The turn state machine (`idle→listening→thinking→speaking→listening`;
`speaking→listening` on barge-in; teardown/re-offer) is **not modified**.
Difference vs 006: the SPEAKING phase begins as soon as the **first** unit is
assembled from the incremental draft (not after the whole reply), and the
agent may still be generating during SPEAKING. Barge-in transition now also
cancels agent generation.

| Transition | 007 effect |
|------------|-----------|
| thinking → speaking | entered when the first speakable unit is assembled from the live draft (FR-001) |
| speaking (per unit) | units assembled from arriving draft updates; per-unit synth + playback overlapped (feature 006) |
| agent still generating | later updates append more units while earlier ones play (FR-002/FR-003) |
| barge-in | stop_playback + cancel pipeline + **Hermes interrupt** → no orphan unit, no orphan generation (FR-004/SC-004) |
| reply done (`finalize`) | flush remaining units; turn-complete bookkeeping unchanged |
| no streaming / fake bridge | feature-006 behaviour verbatim (FR-005 / SC-007) |
