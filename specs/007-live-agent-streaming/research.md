# Phase 0 Research: End-to-End Streaming Conversation

Decisions are grounded in read-only host recon of hermes-agent v0.13.0
(`ssh hermes`) plus the existing 005/006 code. The central feasibility
question is answered; residual exact-API details are resolved at implement
time against the running host (constitution V), with FR-005 as the safety net.

## D1 — Hermes CAN stream agent output to an adapter (feasible)

- **Decision**: Build on Hermes's existing **draft-streaming** adapter hook;
  do not invent a new agent path.
- **Evidence (host recon)**:
  - `~/.hermes/config.yaml`: `streaming: true`, `stream_processing_mode:
    async`, a `streaming:` block — streaming is enabled gateway-wide.
  - `gateway/platforms/base.py`: `supports_draft_streaming(...)` (≈L1336)
    "Whether this adapter supports native streaming-draft updates";
    a streaming-draft update method (≈L1362 "Send or update an animated
    streaming-draft preview") and `edit_message(..., finalize=True)` (≈L1609)
    where `finalize` marks the last edit of a streamed response; "fresh-final
    cleanup" / `got_done` semantics.
  - `gateway/run.py`: "streaming already delivered the body", "streaming
    sends raw text chunks", "per-turn token deltas", `already_sent`,
    `_should_send_voice_reply(..., already_sent=...)` — the run loop drives
    the adapter's streaming hook with growing text and tracks completion.
- **Rationale**: An adapter that returns `True` from
  `supports_draft_streaming` receives the reply as a growing draft (repeated
  update calls, finalized via `edit_message(finalize=True)`/`got_done`). A
  voice adapter consumes those increments instead of editing UI text.
- **Alternatives considered**: gateway-side change to add a new streaming
  callback — rejected (constitution IV; the hook already exists).
  Token-level model-adapter streaming (`agent/*_adapter.py` `astream`) —
  rejected (too low-level / provider-specific; the platform draft hook is the
  sanctioned adapter-facing seam).

## D2 — Increment shape: assume cumulative draft text; assemble units

- **Decision**: Treat each streaming update as the **current full draft**
  (cumulative text so far); a stdlib `IncrementalUnitAssembler` diffs against
  what was already spoken, runs `textseg` segmentation on the *stable* prefix,
  and emits only newly-complete speakable units; an incomplete trailing
  sentence is buffered until the next update or `finalize`.
- **Rationale**: Draft-streaming UIs (Telegram edit-preview) are cumulative
  ("update the preview"); assembling on the stable prefix avoids speaking a
  half-sentence and reuses feature 006's proven segmentation verbatim
  (FR-003, edge: partial tokens). Robust even if increments are deltas
  (append-only is the degenerate cumulative case).
- **Alternatives considered**: speak every delta immediately — rejected
  (half-words/sentences, garbled). Re-synthesize on every update — rejected
  (wasteful, overlap).

## D3 — Barge-in must also cancel agent generation (FR-004)

- **Decision**: Extend feature 006's barge-in: in addition to
  `stop_playback()` + cancelling the synthesis/playback pipeline, invoke
  Hermes's **interrupt** for the in-flight turn so the agent stops producing.
- **Evidence**: `gateway/run.py` references an interrupt path
  ("interrupt sent (if not queue)…"). The adapter already drives the turn via
  `handle_message`; the interrupt mechanism is Hermes-owned (constitution I —
  we trigger it, we don't reimplement cancellation of the agent).
- **Rationale**: Without cancelling generation, an interrupted long answer
  keeps the model running (cost + the spec's "no orphaned background
  generation"). Exact interrupt entrypoint verified at implement time.
- **Alternatives considered**: only stop playback (006 behaviour) — rejected
  (FR-004 explicitly requires generation to stop; SC-004 measures it).

## D4 — Mandatory fallback to feature 006 (FR-005)

- **Decision**: If a turn does not exercise the streaming hook (hook not
  called, `supports_draft_streaming` not honoured for voice/`Platform.LOCAL`,
  or only a single final delivery occurs), behaviour is **exactly feature
  006**: segment the completed reply and stream TTS. The fake bridge always
  takes this path.
- **Rationale**: De-risks the residual host-API uncertainty — the feature is
  provably never worse than 006, and the fake-transport suite is byte-
  identical (SC-007). The streaming path is purely additive.

## D5 — Local testability boundary (constitution V)

- **Decision**: Extract the deterministic logic — turning a sequence of
  (cumulative) text updates into ordered complete speakable units with a
  buffered tail and a `finalize` flush — into stdlib
  `streamasm.IncrementalUnitAssembler`, unit-tested. The draft-hook wiring,
  interrupt, and real agent streaming are host-only and host-proven.
- **Rationale**: Mirrors `media.py` (005) / `textseg.py` (006): test what is
  deterministic without the host; honestly host-prove the rest. Keeps the
  fake suite green and gives FR-001/FR-003 real local coverage.

## D6 — Deploy

- **Decision**: Reuse `deploy/deploy-to-hermes.sh` + `rollback.sh`
  (003/004) **unchanged**; existing post-verify is the gate. End-to-end
  cadence + barge-in-cancels-generation are the host live spoken test.
  Deploy-gate quirk persists: `yes yes | deploy/deploy-to-hermes.sh`.
- **Rationale**: FR-010 / Assumptions — no new deploy mechanism.

## Residual — RESOLVED at implement time (T002, host recon 2026-05-19)

Verified against the running host `~/.hermes/hermes-agent/gateway/platforms/
base.py` + `gateway/stream_consumer.py` + `gateway/run.py` (hermes-agent
v0.13.0), read-only:

- **Draft-streaming opt-in**: `BasePlatformAdapter.supports_draft_streaming(
  self, chat_type: Optional[str] = None, metadata: Optional[Dict] = None) ->
  bool` (base.py:1336), default `False`. `GatewayStreamConsumer._maybe_draft`
  (stream_consumer.py:860) probes it with `chat_type=cfg.chat_type`.
- **Partner update method**: `async send_draft(self, chat_id: str,
  draft_id: int, content: str, metadata=None) -> SendResult`
  (base.py:1355). `content` is the **cumulative accumulated text** for the
  current segment ("a single animated draft frame for the current accumulated
  text", stream_consumer.py:877/`_send_draft_frame`); called repeatedly with
  growing text mid-stream (route at stream_consumer.py:1112-1131). A no-op
  skip fires when `content == _last_sent_text` (confirms cumulative).
- **`edit_message(self, chat_id, message_id, content, *, finalize: bool =
  False) -> SendResult`** (base.py:1609). `finalize=True` = last edit of a
  streamed response (set when `got_done` fires). NOT used on the draft path
  (drafts have no `message_id`); for the satellite the finalize point is the
  **regular `send()`** — drafts deliberately DO NOT set `already_sent`
  (stream_consumer.py:1126-1131 comment), so the gateway's final
  `send(chat_id, content=…)` still fires with the full reply. That `send()`
  is therefore both the streamed-reply finalize AND the FR-005 non-streaming
  fallback delivery (single full text, no draft frames seen).
- **Interrupt entrypoint** (D3 resolved): gateway tracks
  `self._running_agents[session_key]` (run.py:1238);
  `running_agent.interrupt(text)` (run.py:2657) aborts in-flight tool calls
  and exits the agent loop. Default `_busy_input_mode = "interrupt"`
  (run.py:1186) — dispatching the **next** `MessageEvent` (the barge-in
  utterance becoming the next turn via `handle_message`) ALREADY calls
  `running_agent.interrupt()` on the still-running prior agent
  (run.py:2655-2657). So feature 006's barge-in (next utterance → next turn →
  `handle_message`) inherently stops the prior agent; T005 makes this
  explicit/prompt and verifies no orphan generation (FR-004).
- **Mid-turn error surface** (C1/H6 resolved): a provider failure raises
  `AllProvidersUnavailable`, which already propagates out of `tts_stream`
  and is caught in `session._handle_turn` → `TurnOutcome.FAILED` +
  `_notify_failure()` + return to LISTENING — the existing perceptible
  turn-failure path, reused unchanged (no new handler; constitution I/IV).
- **Voice/`Platform.LOCAL` eligibility**: the draft path is gated only by
  `supports_draft_streaming` + transport mode (`auto`/`draft`), not by
  platform; opting in is sufficient. FR-005 fallback covers any turn where
  no `send_draft` frame is seen (single final `send()` only).

Integration shape chosen: `_SatellitePlatformAdapter.supports_draft_streaming
-> True`; `send_draft` feeds cumulative `content` to a per-session
`IncrementalUnitAssembler`; complete units drive feature 006's per-unit
Hermes TTS + transport playback as they arrive; the final `send()` flushes
the assembler (streamed turn) OR, if no draft frame was seen, resolves the
reply exactly as feature 006 (FR-005). The fake bridge exposes no streaming
seam → byte-identical 006 path (SC-007).
