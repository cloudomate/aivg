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

## Residual (resolved at implement time, not blockers)

- Exact name/signature of the `supports_draft_streaming` partner update
  method and the `edit_message` streaming signature on the host
  `BasePlatformAdapter` — read from the running host `gateway/platforms/
  base.py` during implementation (same discipline that fixed the
  `send()`/`Platform`/`MessageEvent` APIs in 003/005).
- Exact Hermes interrupt entrypoint for an in-flight turn (D3).
- Whether voice/`Platform.LOCAL` turns are eligible for the draft hook by
  default or need an opt-in flag; FR-005 fallback covers the negative case.
