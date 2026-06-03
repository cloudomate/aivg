# Quickstart: gRPC downstream TTS decode to canonical 48 kHz PCM

How to build, test, and **prove end-to-end** (Constitution V) that gRPC satellites
now hear clean speech.

## What changed (one sentence)

`GrpcMediaAdapter.send_audio` now decodes the TTS clip to 48 kHz s16 mono PCM
(via PyAV / in-process ffmpeg, same as WebRTC) before queuing, so the existing
gateway 48→16 downsample and client 16→48 upsample operate on real PCM.

## Prerequisites

- The gateway dev env (Python ≥ 3.11) with project deps installed (`av>=11`,
  `grpcio` already declared).
- A gRPC-capable satellite/client (e.g. the C++ `libaivg-sat` with
  `AIVG_SAT_ENABLE_GRPC`, which already does the client-side 16↔48 resampling), or
  the in-repo gRPC integration harness.

## Run the tests

```bash
# Unit — the adapter decode/normalize behavior (fast, no gateway):
pytest tests/unit/test_grpc_media_adapter.py -q

# Integration — full voice turn over gRPC, incl. a non-48 kHz provider clip:
pytest tests/integration/test_grpc_transport_basic.py -q
pytest tests/integration/test_grpc_backpressure.py -q     # bounded queues preserved

# Regression — WebRTC path unaffected by the shared-helper refactor:
pytest tests/unit -q -k "signaling or webrtc"
```

### Unit expectations (after the change)

- A **decodable container** (e.g. a small WAV at 24 kHz mono) pushed to
  `send_audio` yields one or more `AudioChunk` `ServerFrame`s whose decoded audio
  matches the source (correct duration/pitch). **This is the regression guard for
  the bug.**
- **Raw PCM** (no container) → **no** `AudioChunk`, session alive (WebRTC parity).
  *(The pre-existing `test_outbound_pump_emits_audio_serverframe`, which fed raw
  PCM, is updated to feed a container.)*
- **Empty / `<16` bytes / sentinel** → no `AudioChunk`, session alive.
- 500 rapid pushes against a stalled consumer never exceed queue `maxsize`.

## Manual / live proof (Principle V end-to-end gate — REQUIRED before "done")

A real provider clip is rarely already 48 kHz PCM, so this is where the bug
actually bit. The fix is "proven" only after an end-to-end turn, not unit tests
alone.

1. Start the gateway with the gRPC audio transport enabled and a platform whose
   TTS returns a **non-48 kHz** container (the normal case).
2. Connect a gRPC satellite; complete a voice turn that produces a spoken reply.
3. **Confirm**: the reply plays as **clear, natural speech** at correct pitch and
   speed — not noise, not chipmunk/slow.
4. **A/B**: the same reply over WebRTC and over gRPC sound perceptually equivalent.
5. **Barge-in**: interrupt mid-reply → playback stops promptly.
6. **Streaming**: a multi-sentence reply plays in full, in order, without clicks.
7. **Empty/error turn**: a tool-only or providers-unavailable turn plays nothing
   and leaves the session usable for the next turn.

## Rollback

The change is isolated to `transports/grpc/media_adapter.py` (+ the shared
`audio/tts_decode.py` helper and, optionally, the `webrtc/signaling.py` refactor).
Reverting `send_audio` to the prior pass-through restores old behavior; no
data/wire migration is involved.
