# Phase 0 Research: Streaming Spoken Replies

All decisions are forced by the spec, the existing
`session.py`/`hermes_bridge.py`/`AiortcTransport` as built in features
001/005, and the constitution. No open `NEEDS CLARIFICATION` remain.

## D1 — Streaming source: segment the completed reply, don't depend on Hermes streaming

- **Decision**: Obtain the agent reply exactly as today (`agent_turn` →
  completed text), then segment it and pipeline per-sentence TTS + playback.
  Do **not** require Hermes to emit partial/streamed reply text.
- **Rationale**: The user-visible outcome (first words ≤1.5 s, sentence
  cadence — SC-001/002/004) is achieved purely by not synthesizing the whole
  reply before playback starts. The current adapter receives the agent reply
  via the gateway's single `send()` callback (`adapter.py` `_run_agent`); true
  token streaming would need a gateway-side change — out of scope, against
  constitution IV / FR-005 / FR-008, and unproven. Segmenting the completed
  text needs zero Hermes change and still removes the dominant latency (whole-
  reply TTS) and the monologue feel.
- **Alternatives considered**: (a) gateway agent token streaming — rejected
  (requires Hermes changes; FR-008/IV). (b) fixed-size byte chunking of one
  big TTS clip — rejected (TTS still synthesizes the whole reply first → no
  SC-001 win, and chops mid-word).

## D2 — Where streaming lives: a `tts_stream` capability on the bridge seam

- **Decision**: Add `tts_stream(text, *, ctx) -> AsyncIterator[bytes]` to
  `HermesV013Bridge`. `session._respond()` consumes it via a module helper
  that falls back to a single `tts_synthesize()` when the bridge has no
  `tts_stream` (the fake bridge).
- **Rationale**: Keeps segmentation/pipelining behind the constitution-I
  Hermes seam (text orchestration + scheduling; real audio still from Hermes
  TTS). `session.py` change is one loop. The fallback makes
  `FakeHermesBridge`/`UnboundHermesBridge` behave exactly as today, so the
  feature-001 fake-transport suite stays green **without test changes**
  (SC-006 / FR-008). The `MediaTransport` contract is untouched (still
  `send_audio(bytes)` per chunk).
- **Alternatives considered**: segmenting inside `session._respond` —
  rejected (more turn-logic churn, higher fake-suite blast radius, mixes
  orchestration into conversation state). New transport method — rejected
  (transport must stay dumb plumbing; contract frozen by FR-008).

## D3 — Pipelining: bounded look-ahead producer

- **Decision**: `tts_stream` runs a producer task: iterate
  `iter_sentences(text)`, synthesize each unit via the existing
  `tts_synthesize`, push audio into a small bounded `asyncio.Queue`
  (look-ahead depth ~1–2). The generator yields audio in order; the consumer
  (`_respond`) awaits `send_audio(unit)` which (per the 005 fix) blocks for
  that unit's real playback duration, during which the producer is already
  synthesizing the next unit.
- **Rationale**: Overlapping next-unit synthesis (~1–2 s) with current-unit
  playback (~3–5 s for a sentence) keeps audio continuous (SC-002 ≤1 s gap)
  and gets first audio out after only unit #1's synthesis (SC-001). Bounded
  depth avoids synthesizing far ahead of a reply that may be barged-in
  (wasted TTS) and bounds memory.
- **Alternatives considered**: synthesize-all-then-stream (no SC-001 win);
  unbounded look-ahead (wasted synthesis on barge-in; FR-004 intent).

## D4 — Barge-in: abandon in-flight + not-yet-synthesized units (FR-004/SC-003)

- **Decision**: Reuse the existing barge-in path unchanged. On detected
  speech, `session._handle_turn` already `stop_playback()`s and cancels the
  reply pipeline task. Cancelling unwinds the `async for` → the `tts_stream`
  generator's `finally` cancels its producer task and drains its queue, so
  **no** not-yet-played or not-yet-synthesized unit is spoken;
  `stop_playback()` drops the in-flight unit's queued audio in the transport.
- **Rationale**: Feature 005 already proved `stop_playback` + pipeline cancel
  within the barge-in deadline; we only must ensure the new generator cleans
  up deterministically on `GeneratorExit`/`CancelledError`. Keeps SC-003 and
  the "no orphan sentence" edge case without new transport behaviour.
- **Alternatives considered**: a separate cancel signal/flag — rejected
  (Python async generator finalization already gives clean teardown; fewer
  moving parts).

## D5 — Segmentation rules (locally testable, constitution V)

- **Decision**: `textseg.iter_sentences(text)` (stdlib only): split on
  `.?!` / newline boundaries followed by space/EOL; merge a unit shorter than
  a min character threshold into the next (avoid choppy one-word audio);
  don't split inside a decimal (`3.14`) or a short common abbreviation
  (`Mr.`, `e.g.`, `etc.`, `Dr.`, `vs.`, `U.S.`); if a unit exceeds a max
  length with no boundary (run-on), hard-split at the max so playback can
  still start early. Output preserves all non-whitespace text in order.
- **Rationale**: This is the one piece provable without aiortc/av/Hermes →
  unit-tested deterministically (mirrors `media.py` from 005). It is text
  chunking only — explicitly NOT VAD/endpointing/agent (constitution I).
- **Alternatives considered**: an NLP sentence tokenizer dependency —
  rejected (new heavy dep; constitution IV "don't rebuild/import what isn't
  needed"; a small rule set is sufficient for speakable cadence).

## D6 — Short / empty / failure behaviour (FR-006/FR-007)

- **Decision**: Empty/tool-only reply → `iter_sentences` yields nothing →
  generator yields nothing → unchanged "return to listening" (today's
  behaviour). A single short reply → one unit → equivalent to today (no
  regression, SC-005). A unit whose `tts_synthesize` raises → log + skip that
  unit, continue the rest; if the very first unit fails and none succeed, the
  turn ends as today (no broken/zero-length audio).
- **Rationale**: Matches FR-006/FR-007 and the spec edge cases; reuses the
  existing `AllProvidersUnavailable` handling at the turn level for the
  total-failure case.

## D7 — Deploy

- **Decision**: Reuse `deploy/deploy-to-hermes.sh` + `rollback.sh`
  (003/004) **unchanged**; existing post-verify is the gate. Streaming cadence
  is proven by the host live spoken test (US1/US2), not a deploy probe.
  Deploy-gate invocation quirk persists: feed confirmation via
  `yes yes | deploy/deploy-to-hermes.sh` (operator pre-authorized).
- **Rationale**: Spec FR-009 / Assumptions — no new deploy mechanism.
