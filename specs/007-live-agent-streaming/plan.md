# Implementation Plan: End-to-End Streaming Conversation (speak while the agent is still thinking)

**Branch**: `007-live-agent-streaming` | **Date**: 2026-05-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/007-live-agent-streaming/spec.md`

## Summary

Feature 006 streams TTS over the *completed* reply, so the caller still waits
out the full agent composition (live test: ~70 s, almost all agent-think,
before the first word). Phase-0 host recon confirms hermes-agent v0.13.0
**already streams agent output to adapters** via a draft-streaming hook
(`BasePlatformAdapter.supports_draft_streaming()` + a streaming-draft update /
`edit_message(..., finalize=True)` path; `already_sent`/`got_done` + per-turn
token deltas). This feature opts the satellite adapter into that hook, turns
the growing draft text into feature-006 speakable units **as it arrives**, and
extends barge-in to also stop agent generation. If the streaming hook is not
exercised for a given turn, it falls back to feature 006 unchanged (FR-005).
Media transport, signaling, control plane, and turn/state semantics stay
behaviourally compatible; the fake-transport suite stays green.

## Technical Context

**Language/Version**: Python 3.11 (`.venv` 3.11.15; host gateway venv 3.12) —
package `hermes_satellite_adapter`.
**Primary Dependencies**: none new. Reuses the Hermes **draft-streaming**
adapter hook (verified present on the host), Hermes TTS via the existing
bridge seam, feature 006 `textseg`/`tts_stream`, feature 005 media transport,
and features 003/004 deploy/rollback unchanged.
**Storage**: none.
**Testing**: pytest+pytest-asyncio in `.venv`. The deterministic, media-free
piece (incremental-text → speakable-unit assembly) is factored into a
stdlib-only helper and unit-tested; feature 001's fake-transport suite stays
100% green (the fake bridge path is unchanged — streaming is host-only).
End-to-end streaming + barge-in-cancels-generation are host-proven by the
live spoken test (constitution V).
**Target Platform**: `ssh hermes` host (hermes-agent v0.13.0); gateway
in-process adapter; live client LAN-direct (`192.168.4.140:8643/8644`).
**Project Type**: single Python package change (host-only adapter/bridge
seam) + redeploy via existing scripts.
**Performance Goals**: first sentence ≤3 s for a ≥10 s answer (SC-001);
≥60% time-to-first-word reduction vs 006 (SC-002); ≤1.5 s inter-sentence gaps
while generating (SC-003); barge-in ≤300 ms + agent-gen stops ≤1 s (SC-004).
**Constraints**: constitution I/IV — the agent + TTS stay Hermes-owned; we
only **consume** Hermes's own streaming hook (no embedded agent/engine).
FR-009: media transport contract + signaling + control plane + turn/state
semantics behaviourally compatible; FR-005 mandatory graceful fallback to
feature 006; FR-010 reuse the gated reversible deploy.
**Scale/Scope**: one new stdlib helper (`streamasm.py`) + its unit test;
`adapter.py` `_SatellitePlatformAdapter` opts into draft streaming and feeds
increments to the speech pipeline; `hermes_bridge.py`/`session.py` consume an
incremental source (reusing 006's `tts_stream` segmentation) and the barge-in
path also cancels agent generation. `signaling.py`/`AiortcTransport`,
`management.py`, `media.py`, `textseg.py`, contracts, `deploy/*` unchanged.

**Resolved (no NEEDS CLARIFICATION):** Phase-0 recon confirms the streaming
hook exists (see research D1). Exact method names/signatures of the
draft-streaming partner method are **verified against the running host code
during implementation** (constitution V — the same host-API-verification
discipline used for `BasePlatformAdapter` in features 003/005); FR-005
guarantees no-worse-than-006 if a turn does not use the hook.

## Constitution Check

*GATE: must pass before Phase 0; re-checked after Phase 1.*

| # | Principle | Gate | Status |
|---|-----------|------|--------|
| I | Thin Satellite, Gateway-Owned Intelligence (NON-NEGOTIABLE) | We **consume** Hermes's own agent-streaming hook + reuse 006 text segmentation; NO agent/STT/TTS engine embedded; the agent loop stays in Hermes. Barge-in uses Hermes's interrupt to stop *its* generation. | ✅ PASS (reinforces) |
| II | Generic Four-Plane Contract | `MediaTransport` Protocol, models, voice-plane endpoints unchanged; a turn still yields one logical reply, now sourced incrementally. | ✅ PASS |
| III | Separate Control & Voice Connections | Untouched — single voice PC; control WS as-is; no durable control on the voice path. | ✅ PASS |
| IV | Reuse Hermes, Don't Rebuild | Reuses the gateway's existing streaming/draft hook + interrupt, Hermes TTS, 006 pipeline, 005 transport, 003/004 deploy. Nothing reimplemented; no new config/secret. | ✅ PASS |
| V | Research-Backed, Verify Before Relying | Streaming capability host-verified in Phase 0; exact host API re-verified at implement time; locally-provable unit-assembly is unit-tested; end-to-end behaviour host-proven; deploy verified before relied on. | ✅ PASS (reinforces) |

**Result: PASS, no violations.** This is more invasive than 006 (it touches
the agent-consumption seam, not just playback) — see Complexity Tracking;
that is *required* by the binding goal (speak while generating) and is still
"consume Hermes, don't rebuild," so no principle is violated.

## Project Structure

### Documentation (this feature)

```text
specs/007-live-agent-streaming/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/streaming-conversation.md
├── checklists/requirements.md   # (from /speckit-specify)
└── tasks.md                     # /speckit-tasks (NOT created here)
```

### Code changes (this feature)

```text
src/hermes_satellite_adapter/streamasm.py          # NEW — stdlib only, unit-tested
  + IncrementalUnitAssembler: fed growing/append text deltas, emits
    COMPLETE speakable units (reusing textseg.iter_sentences semantics)
    as soon as each is final; buffers an incomplete tail; flush() emits
    the remainder on finalize. Pure/deterministic; NO engine (const. I).

src/hermes_satellite_adapter/adapter.py            # host-only (pragma: no cover)
  ~ _SatellitePlatformAdapter: supports_draft_streaming() -> True; implement
    the draft-streaming update + edit_message(..., finalize=) partner method
    (EXACT name/signature verified vs host base.py at implement time) to
    receive growing reply text; feed deltas to an IncrementalUnitAssembler
    whose units drive the existing per-unit Hermes TTS + transport playback
    (feature 006 path). On barge-in, additionally trigger Hermes's interrupt
    so agent generation stops (FR-004).
  ~ agent bridging: the agent_runner/reply path consumes the incremental
    source instead of one final string; non-streaming turns resolve exactly
    as today (FR-005 fallback).

src/hermes_satellite_adapter/hermes_bridge.py / session.py
  ~ minimal: reply audio may be driven by an incremental unit source; the
    fake bridge (no streaming) keeps the single-chunk/`tts_stream` 006 path
    so the fake-transport suite is byte-identical (FR-009 / SC-007).

tests/unit/test_streamasm.py                        # NEW
  assembler invariants: append-delta unit emission, no half-sentence,
  finalize flush, idempotent finalize, no text lost/dup vs concatenated
  input, empty/whitespace. The locally-provable slice of FR-001/FR-003.
```

`signaling.py`/`AiortcTransport`, `media.py`, `textseg.py`,
`management.py`, contracts, and `deploy/*` are reused **unchanged**. Redeploy
= features 003/004 scripts unchanged (FR-010); existing post-verify is the
gate; end-to-end cadence is the host live spoken test, not a deploy probe.

**Structure Decision**: Smallest viable change that meets the binding goal.
The only deterministically testable-without-host piece (incremental text →
complete speakable units) is isolated in stdlib `streamasm.py` and unit-tested
(constitution V; mirrors `media.py`/`textseg.py`). Streaming is delivered by
**opting into Hermes's existing draft-streaming hook** (constitution IV) and
re-using feature 006's segmentation + pipelined synthesis/playback unchanged —
only the *source* of text becomes incremental and barge-in additionally
cancels Hermes's generation. FR-005's fallback keeps every non-streaming/
fake path exactly as 006/today, so SC-007 holds.

## Complexity Tracking

| Violation/Deviation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Touches the agent-consumption seam (`adapter.py` registration shim + reply bridging), not just playback like 006 | The binding requirement — speak the answer *while the agent is still composing it* — is impossible without consuming the agent's output incrementally; only Hermes's draft-streaming hook provides that | Staying in the 006 playback-only seam cannot reduce time-to-first-word for long answers (the dominant latency is agent composition); no thinner change exists. Still "consume Hermes, don't rebuild" — constitution not violated, only more surface than 006 |
