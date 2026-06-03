# Behavioral Contract: `MediaTransport.send_audio` (downstream TTS normalization)

This feature changes **gateway-internal behavior only** — there is **no external
API, proto, or wire-contract change**. The contract documented here is the
*internal* `MediaTransport.send_audio` behavioral contract that every voice
transport (WebRTC, gRPC, esphome) must satisfy so the gateway stays
transport-uniform (Constitution II).

## Surface

```python
class MediaTransport(Protocol):
    async def send_audio(self, pcm: bytes) -> None: ...
```

`Session` calls `await transport.send_audio(audio)` where `audio` is the bytes
returned by the active platform's `synthesize(text) → bytes` / `tts_stream` — an
**encoded audio container** (provider-native codec/rate/channels), NOT raw PCM.

## Required behavior (all transports)

1. **Decode + normalize**: decode the clip and resample to the canonical internal
   format **s16le, mono, 48 000 Hz** before that audio enters the transport's
   downstream path. (Engine: PyAV / in-process ffmpeg — `av.open` +
   `av.AudioResampler(format="s16", layout="mono", rate=48000)`.)
2. **Equivalence**: for the same input clip, all transports MUST yield the same
   canonical PCM (FR-003). This is guaranteed by sharing one decode helper.
3. **Empty / sentinel**: empty input or `len(pcm) < 16` → emit no audio; return
   normally; session stays open. (Covers `b"__PROVIDERS_UNAVAILABLE__"` and
   tool-only turns.)
4. **Undecodable**: if `av.open` cannot open the bytes → drop the clip, emit no
   audio, do not raise, session stays open.
5. **Partial failure**: a decode error after some frames decoded → already-decoded
   audio MAY be delivered; never raise out of `send_audio`.
6. **No stream stall**: normalization MUST NOT block the merged outbound frame
   stream such that unrelated frames (turn events, transcripts) are delayed beyond
   existing behavior (FR-011).
7. **Pacing / barge-in**: enqueuing onto a bounded queue MUST preserve real-time
   pacing and the existing `stop_playback` (barge-in) semantics.

## gRPC realization (this feature)

- `GrpcMediaAdapter.send_audio` performs steps 1–5, frames the canonical PCM to
  20 ms (1920-byte) frames via `PcmFramer`, and `await self._out.put(frame)` per
  frame (bounded queue → backpressure, step 7).
- `run_outbound_pump` (unchanged) downsamples each canonical frame 48 kHz→16 kHz
  (`audioop.ratecv`, carried state), codec-encodes, and emits one `AudioChunk`
  `ServerFrame`.
- `stop_playback` (unchanged) drains `_out` for prompt barge-in.

## Invariants asserted by tests

- Given a **decodable container** at a **non-48 kHz** source rate, `_out`/the
  emitted `AudioChunk`s reconstruct intelligible audio at correct pitch/duration
  (not noise). *(was the bug)*
- Given **raw PCM** or other non-container bytes → dropped (no `AudioChunk`),
  session alive. *(WebRTC parity)*
- Given **empty** / `< 16` bytes / sentinel → no `AudioChunk`, session alive.
- Bounded queues never exceed their maxsize under a stalled consumer (no
  unbounded growth — preserved from feature 021).
- The `AudioChunk` schema, `codec`, and 16 kHz wire rate are **unchanged**.

## Non-goals (explicitly out of contract scope here)

- No change to the `aivg.satellite.v1` proto or the satellite-facing wire.
- No change to the downstream wire sample rate (stays 16 kHz) or negotiated codecs.
- esphome transport conformance to this contract is tracked separately.
