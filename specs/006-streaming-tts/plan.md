# Implementation Plan: Streaming Spoken Replies (sentence-by-sentence)

**Branch**: `006-streaming-tts` | **Date**: 2026-05-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/006-streaming-tts/spec.md`

## Summary

Today `session._respond()` does: full `agent_turn()` → one `tts_synthesize()`
of the whole reply → one `send_audio()`. Result: long silence then a long
uninterruptible monologue (confirmed live in feature 005). This feature
segments the completed reply into sentence-sized speakable units and
**pipelines** per-unit Hermes TTS with incremental playback, so the first
sentence is heard within ~1.5 s while later sentences are synthesized in the
background. No Hermes streaming dependency is required (we segment the reply
the gateway already returns); the media transport contract, signaling, control
plane, and turn/state machine stay behaviourally compatible, and feature 001's
fake-transport suite stays green via a transparent single-chunk fallback.

## Technical Context

**Language/Version**: Python 3.11 (`.venv` 3.11.15; host gateway venv 3.12) —
package `hermes_satellite_adapter`.
**Primary Dependencies**: none new. Reuses Hermes TTS via the existing
`HermesBridge` seam (per-sentence `tts_synthesize` calls), aiortc/av media
path from 005, and features 003/004 `deploy/`+`rollback.sh` unchanged.
**Storage**: none.
**Testing**: pytest+pytest-asyncio in `.venv`. The deterministic, media-free
piece (sentence segmentation) is factored into a stdlib-only module and
unit-tested locally; feature 001's fake-transport conversation suite stays
100% green (a fallback keeps fake behaviour byte-identical). Real streaming
cadence/barge-in is host-proven by the live spoken test (constitution V).
**Target Platform**: `ssh hermes` host (hermes-agent v0.13.0), gateway
in-process adapter; live client on the LAN (`192.168.4.140:8643/8644`).
**Project Type**: single Python package change + redeploy via existing scripts.
**Performance Goals**: first audible words ≤1.5 s after reply ready (SC-001);
inter-sentence gap ≤1 s, no overlap (SC-002); barge-in ≤300 ms with zero
orphan sentences (SC-003); ≥5-sentence reply natural end-to-end (SC-004).
**Constraints**: constitution I — segmentation is text orchestration only, no
STT/TTS/agent engine embedded; Hermes provider/voice unchanged. FR-008: media
transport contract + signaling + control plane + turn/state semantics
behaviourally compatible; FR-009 reuse the gated reversible deploy.
**Scale/Scope**: deliberately small — one new stdlib module (`textseg.py`) +
its unit test, a `tts_stream` capability on `HermesV013Bridge`, and a minimal
`session._respond` change guarded by a single-chunk fallback. `signaling.py`
media transport, `adapter.py`, `management.py`, contracts, `deploy/*`
unchanged.

**Resolved (no NEEDS CLARIFICATION):** the spec's streaming-source ambiguity
is resolved by design — we segment the **completed** reply text and pipeline
per-sentence TTS + playback (no reliance on Hermes emitting partial text).
This meets every user-visible success criterion (SC-001..SC-007) without a
gateway-side change, keeping constitution IV / FR-005 / FR-008 intact. If
Hermes later exposes incremental reply text, the same `tts_stream` seam can
consume it with no contract change.

## Constitution Check

*GATE: must pass before Phase 0; re-checked after Phase 1.*

| # | Principle | Gate | Status |
|---|-----------|------|--------|
| I | Thin Satellite, Gateway-Owned Intelligence (NON-NEGOTIABLE) | Sentence segmentation + pipeline ordering is pure text/scheduling orchestration — NOT ASR/TTS/agent/endpointing. Each unit's audio is still produced by Hermes TTS via the existing `tts_synthesize` seam; agent + endpointing untouched. | ✅ PASS (reinforces) |
| II | Generic Four-Plane Contract | `MediaTransport` Protocol, shared models, voice-plane endpoints unchanged; a turn still produces one logical reply, now delivered as ordered chunks. | ✅ PASS |
| III | Separate Control & Voice Connections | Untouched — single voice PC, control WS as-is; no durable control moved onto the voice path. | ✅ PASS |
| IV | Reuse Hermes, Don't Rebuild | Reuses Hermes TTS (same provider, per-sentence calls), the 005 media transport, and 003/004 deploy/rollback. Nothing reimplemented; no new config/secret. | ✅ PASS |
| V | Research-Backed, Verify Before Relying | The locally-provable slice (segmentation) is isolated + unit-tested; streaming cadence/barge-in (not locally exercisable) is host-proven by the live spoken test; deploy verified before relied on. | ✅ PASS (reinforces) |

**Result: PASS, no violations.** Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/006-streaming-tts/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/streaming-reply.md
├── checklists/requirements.md   # (from /speckit-specify)
└── tasks.md                     # /speckit-tasks (NOT created here)
```

### Code changes (this feature)

```text
src/hermes_satellite_adapter/textseg.py            # NEW — stdlib only, unit-tested
  + iter_sentences(text) -> list[str]: split into speakable units on
    sentence boundaries; merge sub-threshold fragments; protect decimals
    and common abbreviations; a run-on with no punctuation is chunked by
    a max length so playback can still start early. NO VAD/agent (const. I).

src/hermes_satellite_adapter/hermes_bridge.py
  + HermesV013Bridge.tts_stream(text, *, ctx) -> AsyncIterator[bytes]:
    iter_sentences → bounded look-ahead producer task that calls the
    EXISTING tts_synthesize per unit; yields audio in order; cancels the
    producer + abandons un-synthesized units on generator close (FR-004/7).
  ~ HermesBridge Protocol: document optional tts_stream (structural;
    fakes without it transparently fall back — SC-006).

src/hermes_satellite_adapter/session.py
  ~ _respond(): replace the single tts_synthesize+send_audio with
      async for audio in _reply_audio(self._bridge, reply.text, ctx):
          await self._transport.send_audio(audio)
    where module helper _reply_audio uses bridge.tts_stream if present
    else yields a single tts_synthesize(...) (identical to today for the
    fake bridge → turn/state semantics + fake suite unchanged, FR-008).
    Barge-in path unchanged: pipeline.cancel() unwinds the async-for →
    generator finally abandons remaining units; stop_playback() drains
    the in-flight unit (FR-004 / SC-003).

tests/unit/test_textseg.py                          # NEW
  segmentation invariants: boundary cases, fragment merge, decimal/
  abbreviation protection, run-on chunking, order/coverage (no text
  lost), empty/whitespace. The locally-provable slice of FR-002.
```

`deploy/deploy-to-hermes.sh` + `rollback.sh` reused **unchanged** (FR-009);
existing post-verify (both ports, constitution-I no embedded engines, zero
pre-existing-platform regression) remains the gate. Streaming cadence is
proven by the live spoken test (US1/US2), not a new deploy check.

**Structure Decision**: Smallest viable change. The only deterministically
testable-without-the-media-stack logic (sentence segmentation, FR-002) is
isolated in stdlib `textseg.py` and unit-tested (constitution V mirror of
feature 005's `media.py`). Streaming is added as a `tts_stream` capability on
the Hermes-backed bridge (the constitution-I seam — text chunking +
scheduling, real audio still from Hermes TTS), consumed via a tiny
`session._respond` change whose single-chunk fallback makes the fake-driven
suite behave exactly as before (SC-006). The 005 media transport, signaling,
control plane, models, and deploy scripts are untouched.

## Complexity Tracking

> Not applicable — Constitution Check passed with no violations.
