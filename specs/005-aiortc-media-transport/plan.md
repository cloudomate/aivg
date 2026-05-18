# Implementation Plan: Real WebRTC Media Transport (audio actually flows)

**Branch**: `005-aiortc-media-transport` | **Date**: 2026-05-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/005-aiortc-media-transport/spec.md`

## Summary

Replace the single `NotImplementedError` stub in
`signaling.py::aiortc_transport_factory` with a real `AiortcTransport` that
adapts a live `RTCPeerConnection`'s audio tracks to the **unchanged**
`MediaTransport` Protocol (`receive`/`send_audio`/`stop_playback`/
`connection_state`/`close`). Inbound: decode the caller's Opus track to 16‑bit
mono 48 kHz PCM and hand the conversation loop fixed 20 ms frames. Outbound:
decode whatever the Hermes TTS provider returned (any container/rate, via
`av`), resample to 48 kHz mono, and feed an aiortc outbound Opus track;
`stop_playback()` flushes that buffer for barge-in. Then **gated-redeploy**
through features 003/004's existing `deploy/`+`rollback.sh` (unchanged) so the
long-blocked end-to-end spoken test can finally pass. No change to
`session.py`, the bridge, signaling/control wiring, or the fake-transport
suite.

## Technical Context

**Language/Version**: Python 3.11 (local `.venv` 3.11.15; host gateway venv
3.12) — single package `hermes_satellite_adapter`.
**Primary Dependencies**: `aiortc` (RTCPeerConnection / audio
`MediaStreamTrack`) and `av`/PyAV (Opus⇄PCM decode/encode, resample,
container sniffing) — both already present on the Hermes host (verified
feature 003 preflight), lazy-imported so the package still imports and the
fake suite still runs without them locally. `aiohttp` signaling site reused
unchanged (feature 004).
**Storage**: none.
**Testing**: pytest + pytest-asyncio in `.venv`. The real media path cannot be
exercised locally (aiortc/av are not local test deps); the pure
**frame/format** logic is factored into a stdlib-only helper that *is*
unit-tested locally. Real-path correctness is proven on the host by the live
spoken test (constitution V). Feature 001's fake-transport suite stays 100%
green (SC-008).
**Target Platform**: `ssh hermes` host, hermes-agent v0.13.0; adapter runs
in-process in the gateway (`SatelliteWebRTCAdapter`).
**Project Type**: single Python package change + redeploy via existing scripts.
**Performance Goals**: spoken reply begins ≤1.5 s after end-of-speech
(SC-003); barge-in stops outbound audio ≤300 ms (SC-004); ≥3 clean
consecutive turns, no progressive desync (SC-006).
**Constraints**: transport stays a *thin* media adapter — no STT/TTS/agent/
endpointing embedded (constitution I / FR-008/FR-011); `MediaTransport`
interface and `session.py` byte-unchanged (FR-003/FR-012); wire = Opus 48 kHz
mono; internal = s16le mono at the rate the bridge expects (48 kHz, 20 ms
frames — matches `HermesV013Bridge` defaults); reuse the gated reversible
deploy, no new mechanism (FR-009).
**Scale/Scope**: deliberately tiny — `signaling.py` (real `AiortcTransport` +
factory body), one new stdlib-only helper module `media.py` (testable
PCM framing/format reconciliation), one new unit test file. `session.py`,
`hermes_bridge.py`, `adapter.py`, `management.py`, the contracts, and
`deploy/*` are untouched.

**Resolved (no NEEDS CLARIFICATION):** wire/internal audio formats are pinned
by feature 001's design contract and `HermesV013Bridge` (Opus 48 kHz mono ↔
s16le mono 48 kHz, 20 ms frames); format reconciliation library is `av` (spec
Assumptions); deploy/rollback mechanism verified live in features 003/004 and
reused unchanged.

## Constitution Check

*GATE: must pass before Phase 0; re-checked after Phase 1.*

| # | Principle | Gate | Status |
|---|-----------|------|--------|
| I | Thin Satellite, Gateway-Owned Intelligence (NON-NEGOTIABLE) | `AiortcTransport` only decodes/encodes/buffers audio; it MUST NOT do VAD/endpointing/STT/TTS/agent — those stay behind `HermesBridge`. The `media.py` framer is pure reshaping (split/pad bytes), explicitly *not* VAD. | ✅ PASS (reinforces) |
| II | Generic Four-Plane Contract | `MediaTransport` Protocol, `SatelliteState`/models, and the voice-plane endpoint set are unchanged; only the voice-plane *realisation* gains a real backer. | ✅ PASS |
| III | Separate Control and Voice Connections | Untouched — single voice `RTCPeerConnection`; no durable control moved onto it; control WS / signaling site as-is (feature 004). | ✅ PASS |
| IV | Reuse Hermes, Don't Rebuild | Uses host-resident aiortc/av; reuses `session.py` loop, the bridge seam, feature 003/004 deploy/rollback. Nothing reimplemented. | ✅ PASS |
| V | Research-Backed, Verify Before Relying | Real WebRTC media isn't locally testable → correctness proven by the host live spoken test; locally-testable format/framing logic is isolated and unit-tested; deploy verified before relied on. | ✅ PASS (reinforces) |

**Result: PASS, no violations.** Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/005-aiortc-media-transport/
├── plan.md            # this file
├── research.md        # Phase 0 — format/codec/teardown decisions
├── data-model.md      # Phase 1 — transport-internal entities/state
├── quickstart.md      # Phase 1 — deploy + live spoken test runbook
├── contracts/
│   └── aiortc-media-transport.md   # MediaTransport realisation contract
├── checklists/requirements.md      # (from /speckit-specify)
└── tasks.md           # /speckit-tasks (NOT created here)
```

### Code changes (this feature)

```text
src/hermes_satellite_adapter/media.py            # NEW — stdlib only, unit-tested
  + PcmFramer: split an arbitrary PCM byte stream into fixed N-byte
    (20 ms s16le mono @ 48 kHz = 1920 B) frames, buffering remainders;
    flush() pads the tail with silence. No VAD (constitution I).
  + frame_bytes(sample_rate, ms, channels=1, width=2) -> int  (helper)

src/hermes_satellite_adapter/signaling.py
  ~ aiortc_transport_factory(offer_sdp, device_id):
        build RTCPeerConnection (answerer), setRemoteDescription(offer),
        attach an outbound audio track, createAnswer/setLocalDescription,
        wait for the inbound audio track (fail clearly if none), return
        (answer_sdp, AiortcTransport(pc, in_track, out_track))
  + class AiortcTransport (implements session.MediaTransport):
        receive()         -> next 20 ms s16le PCM frame, None on track end/close
        send_audio(pcm)   -> av-decode→48k mono→enqueue on the outbound track
        stop_playback()   -> flush outbound queue (barge-in ≤300 ms)
        connection_state  -> mapped from pc.connectionState
        close()           -> stop tracks + pc.close(); idempotent

tests/unit/test_media_framer.py                  # NEW
  framing/padding/format-reconciliation invariants on PcmFramer
  (the locally-testable slice of FR-004); fake suite untouched
```

`deploy/deploy-to-hermes.sh` and `deploy/rollback.sh` are **reused unchanged**
(FR-009). Their post-verify already asserts both planes listen + constitution-I
(no embedded speech engines) + zero pre-existing-platform regression; that
remains the deploy gate. Media correctness is proven by the live spoken test
(US4 / quickstart), not by adding a new deploy mechanism.

**Structure Decision**: Smallest viable change at the exact stub site. The only
genuinely testable-without-the-media-stack logic (PCM (re)framing & format
reconciliation, FR-004) is extracted into a stdlib-only `media.py` so it gets
real local coverage while the rest is honestly host-proven (constitution V).
The `MediaTransport` Protocol is the seam — implementing a real backer requires
zero change to `session.py`, the bridge, or the fake suite (FR-003/FR-012).

## Complexity Tracking

> Not applicable — Constitution Check passed with no violations.
