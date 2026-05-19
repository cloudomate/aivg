# Phase 1 Data Model: Streaming Spoken Replies

No persisted data, no new shared models. Feature 001/005 entities
(`VoiceSession`, `ConversationTurn`, `MediaTransport`, `HermesBridge`,
`AiortcTransport`) are reused **behaviourally unchanged** (FR-008). The
entities below are transport-/bridge-internal runtime constructs.

## Entity: Speakable Unit (`textseg.iter_sentences`)

A sentence-sized chunk of reply text, produced in order.

| Aspect | Rule |
|--------|------|
| Boundary | split after `.`/`?`/`!`/newline when followed by whitespace or end |
| Min size | a unit shorter than `MIN_CHARS` is merged into the following unit (no choppy one-word audio) |
| Decimal guard | no split inside digits-dot-digits (`3.14`) |
| Abbrev guard | no split after a short known abbreviation (`Mr. Dr. e.g. etc. vs. U.S. …`) |
| Run-on cap | a unit with no boundary exceeding `MAX_CHARS` is hard-split at `MAX_CHARS` so playback can begin early |
| Coverage | concatenating the units (with single spaces) loses no non-whitespace content; order preserved |
| Empty | empty/whitespace-only input → no units |

`iter_sentences(text: str) -> list[str]` — pure, deterministic, stdlib only,
no VAD/endpointing/agent (constitution I). Locally unit-tested.

## Entity: Reply Stream (`HermesBridge.tts_stream`)

`tts_stream(text: str, *, ctx: SessionCtx) -> AsyncIterator[bytes]`

| Field/behaviour | Description |
|-----------------|-------------|
| units | `iter_sentences(text)` in order |
| producer | background task: for each unit, `await tts_synthesize(unit, ctx)`; push audio to a bounded `asyncio.Queue` (look-ahead depth 1–2) |
| yield order | strictly in unit order; consumer paces by awaiting `send_audio` per chunk |
| unit failure | `tts_synthesize` raising for a unit → log, skip that unit, continue (FR-007) |
| total failure | first units all fail / `AllProvidersUnavailable` → propagate as today (turn-level handling unchanged) |
| close/cancel | on `GeneratorExit`/`CancelledError`: cancel producer, drain queue, synthesize nothing further (FR-004) |
| optionality | structural capability; a bridge without `tts_stream` (fakes) is handled by the consumer's single-chunk fallback |

## Entity: Reply Audio Helper (`session._reply_audio`)

Module-level async generator used by `_respond`:

```
async def _reply_audio(bridge, text, ctx):
    stream = getattr(bridge, "tts_stream", None)
    if stream is not None:
        async for audio in stream(text, ctx=ctx):
            yield audio
    else:
        yield await bridge.tts_synthesize(text, ctx=ctx)   # today's behaviour
```

- With the **fake** bridge (no `tts_stream`): exactly one chunk == current
  behaviour → feature-001 fake-transport suite green, no test changes
  (SC-006 / FR-008).
- With `HermesV013Bridge`: streamed units.

## State / lifecycle (reused, unchanged)

The turn state machine (`idle→listening→thinking→speaking→listening`;
`speaking→listening` on barge-in; teardown/re-offer) is **not modified**.
`_respond` still: sets `SPEAKING`, emits the reply, returns. Difference:
`send_audio` is now called once per speakable unit instead of once per reply;
each call (per the 005 drain fix) blocks for that unit's playback so the
barge-in watcher stays live across the whole streamed reply.

| Transition | Streaming effect |
|------------|------------------|
| thinking → speaking | unchanged; entered once when first unit is ready |
| speaking (per unit) | `send_audio(unit)` blocks for that unit's playback; producer synthesizes next unit meanwhile |
| barge-in (speaking → listening) | pipeline cancel → generator abandons remaining + un-synthesized units; `stop_playback()` drops in-flight unit audio (SC-003) |
| reply complete → listening | after the last unit drains; unchanged turn-complete bookkeeping |
