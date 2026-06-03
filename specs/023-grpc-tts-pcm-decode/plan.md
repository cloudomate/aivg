# Implementation Plan: gRPC downstream TTS decode to canonical 48 kHz PCM

**Branch**: `023-grpc-tts-pcm-decode` | **Date**: 2026-06-03 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/023-grpc-tts-pcm-decode/spec.md`

## Summary

The gRPC voice transport's outbound path queues the **raw, provider-encoded TTS
clip** straight into its 48 kHz PCM queue (`GrpcMediaAdapter._out`) and then runs
its standard 48 kHz→16 kHz downsample over those bytes — but the bytes were never
48 kHz PCM, so the satellite plays noise. The WebRTC transport
(`webrtc/signaling.py:send_audio`) already does the correct thing: `av.open` the
clip and resample to s16/mono/48 kHz before framing. This feature gives the gRPC
adapter the **same decode-and-resample-to-48 kHz step**, so `_out` finally holds
true 48 kHz PCM and the existing downstream resampling (gateway 48→16, client
16→48) becomes correct end-to-end. Internal-only: no proto/wire change, no
client change.

**Approach**: In `GrpcMediaAdapter.send_audio(pcm)`, decode the clip with PyAV
(`av.open` + `av.AudioResampler(format="s16", layout="mono", rate=48000)`), frame
the decoded PCM to 20 ms with the existing `PcmFramer`, and enqueue each 1920-byte
48 kHz frame into `_out`. `run_outbound_pump` (the 48→16 downsample + codec encode
+ `ServerFrame`), `stop_playback`, `close`, and `ui_event_sink` are unchanged. To
stop the two transports from silently diverging again (the root cause), the
decode is extracted into one neutral helper that both transports call.

## Technical Context

**Language/Version**: Python ≥ 3.11 (gateway `aivg_core`)
**Primary Dependencies**: PyAV (`av>=11`, already a project dep — `av.open` +
`av.AudioResampler`); stdlib `audioop` (existing 48→16 downsample, unchanged);
`PcmFramer` (`aivg_core.webrtc.media`); `grpcio` (existing)
**Storage**: N/A
**Testing**: `pytest` + `pytest-asyncio` — unit
`tests/unit/test_grpc_media_adapter.py`, integration
`tests/integration/test_grpc_transport_basic.py`,
`tests/integration/test_grpc_backpressure.py`
**Target Platform**: Linux gateway (server-side)
**Project Type**: Single project (Python gateway service/library under `src/aivg_core/`)
**Performance Goals**: Real-time voice; decode keeps pace with playback; per-clip
decode cost negligible vs. real-time playback duration; no added perceptible
latency to first audio frame
**Constraints**: MUST NOT block/stall the merged `ServerFrame` stream so that turn
events/transcripts are delayed (FR-011); bounded queues preserved (no unbounded
growth, FR-021 from feature 021); barge-in latency unchanged; undecodable/empty
input never raises out of `send_audio`
**Scale/Scope**: One small adapter method + one extracted helper + tests. One
decode per TTS clip/unit; ~1–3 source files touched in `src/`, ~2–3 test files.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Thin Satellite, Gateway-Owned Intelligence (NON-NEGOTIABLE)** — ✅ PASS.
  This is gateway-side **transport audio plumbing** (decode/resample of audio the
  active platform's `synthesize(text) → audio` already produced), explicitly *not*
  STT/TTS. It introduces no STT/TTS engine; it mirrors the WebRTC path whose own
  code is documented "Pure audio plumbing only — decode/encode/resample/buffer. NO
  STT/TTS." No Piper/Whisper introduced.
- **II. Generic Four-Plane Contract** — ✅ PASS / strengthens. The gateway must be
  identical across device types and MUST NOT branch by `device_type`. This change
  makes the gRPC voice plane honor the *same* canonical internal representation
  (48 kHz s16 mono PCM) the WebRTC plane already uses, removing a per-transport
  divergence rather than adding one. No gateway branching introduced.
- **III. Separate Control and Voice Connections** — ✅ PASS. Voice-plane audio
  *content* only; no change to connection topology, `Audio.Stream` framing, or
  control/voice separation. Audio frames still ride `Audio.Stream` as before.
- **IV. Reuse the Upstream Agent Platform** — ✅ PASS. TTS bytes come from the
  platform plugin's `synthesize`; we only normalize their container/rate for
  transport. No TTS reimplementation.
- **V. Research-Backed, Constraint-Driven Decisions** — ✅ PASS. The 48 kHz
  canonical / 16 kHz wire boundary is the established, constraint-driven contract
  (matches WebRTC, XVF3800 48 kHz note). Per Principle V the fix MUST be proven
  **end-to-end** on real provider audio (not just unit-tested) before being
  declared done — captured as an explicit validation gate in quickstart.md.

**Result**: PASS — no violations, no Complexity Tracking entries required.

## Project Structure

### Documentation (this feature)

```text
specs/023-grpc-tts-pcm-decode/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output (incl. the Principle V end-to-end gate)
├── contracts/
│   └── media-transport-send-audio.md   # behavioral contract for send_audio
└── tasks.md             # /speckit-tasks output (NOT created here)
```

### Source Code (repository root)

```text
src/aivg_core/
├── audio/
│   └── tts_decode.py          # NEW — neutral shared decode helper:
│                              #   decode_tts_to_pcm48k(pcm) -> bytes (s16 mono 48k)
│                              #   (single canonical home so transports can't diverge)
├── webrtc/
│   ├── media.py               # PcmFramer lives here (reused, unchanged)
│   └── signaling.py           # send_audio refactored to call the shared helper
│                              #   (optional consolidation; guarded by WebRTC tests)
└── transports/
    └── grpc/
        └── media_adapter.py   # CHANGED — send_audio decodes via the helper +
                               #   PcmFramer, enqueues 48 kHz frames into _out;
                               #   run_outbound_pump / stop_playback / close unchanged

tests/
├── unit/
│   └── test_grpc_media_adapter.py   # CHANGED — feed a decodable container (WAV)
│                                    #   instead of raw PCM; + empty/undecodable cases
└── integration/
    ├── test_grpc_transport_basic.py # extend — full turn with non-48k provider clip
    └── test_grpc_backpressure.py    # keep green — bounded-queue behavior preserved
```

**Structure Decision**: Single-project Python gateway. The change is localized to
the gRPC transport adapter (`src/aivg_core/transports/grpc/media_adapter.py`). The
canonical TTS-decode logic is lifted into one neutral module
(`src/aivg_core/audio/tts_decode.py`) that both the gRPC adapter and (optionally)
`webrtc/signaling.py` call, so the two transports normalize audio identically and
this bug class cannot silently recur. `PcmFramer` stays in `webrtc/media.py`
(transport-neutral already; no churn).

## Complexity Tracking

> No Constitution Check violations — section intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| (none) | — | — |
