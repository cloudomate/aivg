# Phase 1 Data Model: Agent Text-Delta Streaming Seam

No persisted data, no new shared models. Features 001/005/006/007 entities are
reused behaviourally unchanged (FR-009). New constructs are runtime-only.

## Entity: `IncrementalUnitAssembler` (reused from feature 007, UNCHANGED)

`streamasm.py` — reused verbatim (FR-011). Turns a sequence of text deltas
(cumulative OR append) into ordered complete speakable units with a buffered
tail and idempotent `flush()`; immutable already-emitted prefix. Its unit
suite (`tests/unit/test_streamasm.py`) is reused with **no edits**.

| Member | Description |
|--------|-------------|
| `push(draft: str) -> list[str]` | accept the latest delta (cumulative or append); return newly-complete units |
| `flush(final_text=None) -> list[str]` | finalize: remaining buffered unit(s); idempotent (2nd → []) |

## Entity: Incremental Reply Source (bridge/adapter seam — host-only)

`HermesV013Bridge.agent_stream(user_text, *, ctx, turn=None)` —
**rewritten** (host-only, `pragma: no cover`):

| Aspect | Behaviour (008) |
|--------|-----------------|
| agent entrypoint | `from run_agent import AIAgent` (lazy). Construct an `AIAgent` mirroring `cli.py` (model/fallback/toolsets/session from Hermes config — no provider/config invented here; constitution IV). |
| run | `agent.run_conversation(user_text, stream_callback=cb)` executed in a worker thread (blocking, like cli.py); `cb(delta)` is the text-delta sink. |
| delta → speech | `cb(delta)` → `IncrementalUnitAssembler.push(delta)`; each completed unit → existing `tts_synthesize` (Hermes Piper) → audio yielded in order (feature 006 per-unit pipeline). |
| done | agent run returns → `assembler.flush(final_text)` → remaining units spoken; turn reply complete; bookkeeping unchanged. |
| barge-in | `AIAgent.interrupt()` on the in-flight agent + abandon the unit queue + feature-006 stop_playback (FR-004). |
| failure mid-stream | agent/TTS exception surfaces through the existing turn-level handling (perceptible failure, return to listening) — no hang (FR-008). |
| no stream / fake bridge | `agent_stream` absent (fake) or AIAgent unavailable → fall back: resolve exactly as feature 006 (`agent_turn` + `tts_stream`) — FR-005. |

Exact `AIAgent`/`run_conversation`/`interrupt` signatures verified against the
running local `run_agent.py`/`cli.py` v0.14.0 (research D2/D5; constitution V).

## Entity: Voice Session / Turn (reused, unchanged)

The turn state machine (`idle→listening→thinking→speaking→listening`;
`speaking→listening` on barge-in; teardown/re-offer) is **not modified**
(FR-009). Difference vs 006: SPEAKING begins as soon as the **first** unit is
assembled from the agent's live delta stream (not after the whole reply); the
agent may still be generating during SPEAKING; barge-in additionally calls
`AIAgent.interrupt()`.

| Transition | 008 effect |
|------------|-----------|
| thinking → speaking | entered when the first speakable unit is assembled from the agent delta stream (FR-002) |
| speaking (per unit) | units assembled from arriving deltas; per-unit synth + playback overlapped (feature 006) |
| agent still generating | later deltas append more units while earlier ones play (FR-002/FR-003) |
| barge-in | stop_playback + cancel pipeline + **`AIAgent.interrupt()`** → no orphan unit, no orphan generation (FR-004/SC-004) |
| reply done | flush remaining units; turn-complete bookkeeping unchanged |
| no stream / fake bridge | feature-006 behaviour verbatim (FR-005 / SC-007) |
