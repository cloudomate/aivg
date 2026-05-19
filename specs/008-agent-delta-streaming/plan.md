# Implementation Plan: Stream the Spoken Answer via the Agent Text-Delta Seam

**Branch**: `008-agent-delta-streaming` | **Date**: 2026-05-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/008-agent-delta-streaming/spec.md`

## Summary

Feature 007 tried to obtain the reply incrementally via Hermes's platform
**draft-streaming hook**; live `-vv` debugging on the local Hermes install
(v0.14.0) proved that hook is **never driven** for the satellite's
programmatic/voice path (`GatewayStreamConsumer` is never instantiated;
`supports_draft_streaming`/`send_draft` never invoked). Hermes's own CLI and
Discord voice modes get streaming a different, sanctioned way: they **run the
Hermes agent directly with a text-delta callback**. This feature re-sources the
reply through that proven seam — construct/run the Hermes `AIAgent`
(`from run_agent import AIAgent`) with a `stream_callback`/
`stream_delta_callback`, feed the deltas into feature 007's existing
`IncrementalUnitAssembler`, and drive feature 006's per-sentence Hermes-TTS →
WebRTC playback as the agent generates. Barge-in calls `AIAgent.interrupt()`.
STT (`transcription_tools.transcribe_audio`) and TTS (`tts_tool`/Piper) are the
same Hermes calls we already use. If running the agent with a delta sink is
unavailable for a turn (or the fake bridge), behaviour falls back to feature
006 verbatim (FR-005). Supersedes feature 007's draft-hook path; reuses 007's
assembler + unit tests unchanged.

## Technical Context

**Language/Version**: Python 3.11 (`.venv` 3.11.15; local host gateway venv
3.11.15) — package `hermes_satellite_adapter`.
**Primary Dependencies**: none new. Reuses Hermes `run_agent.AIAgent` (the
same class/entrypoints `cli.py`/Discord voice use — verified on the running
local v0.14.0 host), Hermes STT `transcription_tools.transcribe_audio`, Hermes
TTS `tts_tool` (Piper) via the existing bridge, feature 007 `streamasm`,
feature 006 segmentation/pipeline, feature 005 media transport, and the local
deploy script.
**Storage**: none.
**Testing**: pytest+pytest-asyncio in `.venv`. The deterministic media-free
piece (`IncrementalUnitAssembler`) is reused from feature 007 with its unit
suite **unchanged**; feature 001's fake-transport suite stays 100% green with
**no test edits** (fake bridge has no agent-stream seam → feature-006 path).
End-to-end streaming + barge-in are host-proven by the local live spoken test
(constitution V).
**Target Platform**: **local** Hermes install (hermes-agent v0.14.0,
`~/.hermes/hermes-agent`); gateway in-process adapter; client localhost
(`127.0.0.1:8643/8644`), all-localhost so WebRTC media works.
**Project Type**: single Python package change (host-only bridge/adapter
agent-run seam) + redeploy via `deploy/deploy-local.sh`.
**Performance Goals**: first sentence ≤3 s for a ≥10 s answer (SC-001); ≥60%
time-to-first-word reduction vs 006 (SC-002); ≤1.5 s inter-sentence gaps
(SC-003); barge-in ≤300 ms + agent-gen stops ≤1 s (SC-004).
**Constraints**: constitution I/IV — STT/agent/TTS stay Hermes-owned, reached
the SAME way Hermes's own voice modes reach them (we run Hermes's `AIAgent`,
not a reimplemented loop). FR-009: transport contract + signaling + control
plane + turn/state semantics behaviourally compatible; FR-005 mandatory
fallback to feature 006; FR-010 reuse the local reversible deploy.
**Scale/Scope**: rewrite `hermes_bridge.py` `agent_stream` to run `AIAgent`
directly with a delta sink (replacing the feature-007 `send_draft`/
`handle_message`+future streaming path); barge-in → `AIAgent.interrupt()`;
`adapter.py` drops the now-dead draft-hook methods (`supports_draft_streaming`/
`send_draft`/`feed_draft` glue) or leaves them inert; `session.py` `_respond`
unchanged (already prefers `agent_stream`, falls back to 006). `streamasm.py` +
`test_streamasm.py`, `signaling.py`, `media.py`, `textseg.py`,
`management.py`, contracts, `deploy/*` unchanged.

**Resolved (no NEEDS CLARIFICATION):** Phase-0 host recon (research.md)
pinned the exact v0.14.0 entrypoints: `from run_agent import AIAgent`;
`AIAgent.__init__(..., stream_delta_callback=…)`; `AIAgent.run_conversation(
user_message, system_message=None, conversation_history=None, task_id=None,
stream_callback=None, persist_user_message=None) -> dict`;
`AIAgent.interrupt(message=None)`; `AIAgent.is_interrupted()`. FR-005
guarantees no-worse-than-006 if the seam is unavailable for a turn.

## Constitution Check

*GATE: must pass before Phase 0; re-checked after Phase 1.*

| # | Principle | Gate | Status |
|---|-----------|------|--------|
| I | Thin Satellite, Gateway-Owned Intelligence (NON-NEGOTIABLE) | We **run Hermes's own `AIAgent`** + Hermes STT/TTS exactly as Hermes's `cli.py`/Discord voice modes do; we only supply the delta sink, transport, and the abort signal. NO agent/STT/TTS engine reimplemented; the agent loop stays Hermes's `run_conversation`. Barge-in uses Hermes's own `AIAgent.interrupt()`. | ✅ PASS (reinforces) |
| II | Generic Four-Plane Contract | `MediaTransport` Protocol, models, voice-plane endpoints unchanged; a turn still yields one logical reply, now sourced incrementally from the agent's own delta stream. | ✅ PASS |
| III | Separate Control & Voice Connections | Untouched — single voice PC; control WS as-is. | ✅ PASS |
| IV | Reuse Hermes, Don't Rebuild | Uses the **same** `run_agent.AIAgent` entrypoints Hermes itself uses for voice; reuses 007 assembler, 006 pipeline, 005 transport, local deploy. No new config/secret. The discarded 007 gateway-hook code is removed, not replaced with a reimplementation. | ✅ PASS (reinforces) |
| V | Research-Backed, Verify Before Relying | Exact v0.14.0 `AIAgent`/`run_conversation`/`interrupt` entrypoints verified against the running local host in Phase 0 (recorded in research.md); re-verified at implement time; assembler unit-tested; end-to-end host-proven; local deploy verified before relied on. | ✅ PASS (reinforces) |

**Result: PASS, no violations.** This runs the Hermes agent in-adapter rather
than via `handle_message` — see Complexity Tracking; that is *exactly the
pattern Hermes's own CLI/Discord voice modes use* (constitution IV explicitly
sanctions "plugs in like the existing adapters"), so no principle is violated,
only a different (and Hermes-native) agent entrypoint than feature 006/007.

## Project Structure

### Documentation (this feature)

```text
specs/008-agent-delta-streaming/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/agent-delta-streaming.md
├── checklists/requirements.md   # (from /speckit-specify)
└── tasks.md                     # /speckit-tasks (NOT created here)
```

### Code changes (this feature)

```text
src/hermes_satellite_adapter/hermes_bridge.py     # host-only (pragma: no cover)
  ~ agent_stream(): REWRITTEN to run Hermes AIAgent directly —
      from run_agent import AIAgent (lazy); construct like cli.py
      (model/toolsets/session from Hermes config); run_conversation(
      user_text, stream_callback=cb) in a worker thread; cb(delta) →
      IncrementalUnitAssembler.push(); completed units → existing
      tts_synthesize (Hermes Piper) → yield audio. flush() on done.
      Barge-in: AIAgent.interrupt() + abandon queue (FR-004).
  ~ keep tts_stream (006) + agent_turn (handle_message) as the FR-005
    fallback path; fake bridge still exposes neither agent_stream nor a
    streaming seam → feature-006 verbatim (SC-007).

src/hermes_satellite_adapter/adapter.py           # host-only (pragma: no cover)
  ~ remove the feature-007 draft-hook glue (supports_draft_streaming,
    send_draft, send→feed_final, _satellite_request_interrupt) — dead on
    this build; the F007 INFO probes are removed with it. The bridge now
    owns the agent run, so the handle_message+send-future shim is no
    longer the streaming path (kept only if still needed for the 006
    fallback's agent_turn).

src/hermes_satellite_adapter/session.py
  ~ unchanged: _respond already prefers bridge.agent_stream and falls
    back to feature-006 _reply_audio when absent.

src/hermes_satellite_adapter/streamasm.py + tests/unit/test_streamasm.py
  reused UNCHANGED (FR-011).
```

`signaling.py`/`AiortcTransport`, `media.py`, `textseg.py`,
`management.py`, contracts (001/005/006), and `deploy/*` are reused
**unchanged**. Redeploy = `deploy/deploy-local.sh` unchanged (FR-010);
end-to-end cadence is the local host live spoken test.

**Structure Decision**: Smallest change that reaches the binding goal via the
*proven* seam. The deterministic slice (`streamasm.py`) and its tests are
reused untouched from feature 007. Streaming is delivered by running Hermes's
own `AIAgent` with a delta callback — the identical mechanism Hermes's
`cli.py`/Discord voice modes use (constitution IV) — feeding feature 006's
unchanged segmentation/synth/playback. FR-005's fallback keeps every
non-streaming/fake path exactly as 006, so SC-007 holds.

## Complexity Tracking

| Violation/Deviation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| The adapter runs Hermes's `AIAgent` directly (via `run_conversation` with a delta sink) instead of going through `BasePlatformAdapter.handle_message` | The binding goal — speak while the agent composes — requires the agent's incremental text stream; Hermes exposes that stream **only** to code that runs the agent with a delta callback (CLI/Discord voice). The `handle_message`+gateway-stream-consumer path was proven (007, `-vv` DEBUG) to never stream to a programmatic voice adapter. | Staying on `handle_message` cannot stream (empirically proven dead). Running `AIAgent` directly is **not** a reimplementation — it is the exact Hermes-native entrypoint `cli.py`/`discord.py` voice modes use; constitution IV explicitly sanctions adapter-side orchestration calling Hermes's engines. Only the agent *entrypoint* differs from 006/007. |
