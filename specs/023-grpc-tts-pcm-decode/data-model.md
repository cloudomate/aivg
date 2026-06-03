# Data Model: gRPC downstream TTS decode to canonical 48 kHz PCM

This feature defines no persisted entities and no new wire/proto messages. The
"data" here is **audio buffers in flight** and the format invariants at each hop.

## Audio representations (transformations, not stored entities)

### 1. TTS clip (downstream input)
- **What**: the provider-encoded reply audio returned by the active platform's
  `synthesize(text) → bytes` (or `tts_stream`), handed to the transport via
  `MediaTransport.send_audio(pcm: bytes)`.
- **Shape**: an encoded **container** (e.g. WAV / MP3 / Opus) at the provider's
  native sample rate and channel count. **Not** raw PCM.
- **Validity / handling**:
  - empty or `len < 16` bytes → emit nothing (sentinel/empty turn).
  - not openable by `av.open` → drop, session stays alive.
  - opens but errors mid-decode → keep already-decoded audio, never raise.

### 2. Canonical internal PCM (post-decode)
- **What**: the decoded, resampled audio.
- **Shape**: **signed 16-bit little-endian, mono, 48 000 Hz** PCM.
- **Invariant (the fix)**: everything placed on `GrpcMediaAdapter._out` MUST be in
  this format. Today the queue's docstring claims 48 kHz but the code queues the
  raw clip; this feature makes the claim true.
- **Framing**: emitted as uniform **20 ms / 1920-byte** frames via `PcmFramer`;
  a trailing partial frame is zero-padded (digital silence only — Principle I).

### 3. Wire downstream PCM (post-downsample, unchanged)
- **What**: what `run_outbound_pump` produces from the canonical PCM.
- **Shape**: **16 kHz** s16 mono (then optionally codec-encoded), wrapped in an
  `AudioChunk` `ServerFrame` with a monotonic `seq`.
- **Unchanged**: produced by the existing `audioop.ratecv` 48 kHz→16 kHz
  downsample with carried `_downsample_state`; schema and rate are not modified.

## Format invariants (the contract this feature enforces)

| Hop | Producer | Format | Changed by this feature? |
|-----|----------|--------|--------------------------|
| `send_audio(pcm)` input | platform `synthesize` | encoded container, any rate/channels | No |
| `_out` queue items | `send_audio` (NEW decode) | **s16 mono 48 kHz, 1920-byte frames** | **Yes — now true** |
| `AudioChunk.payload` | `run_outbound_pump` | s16 mono 16 kHz (± codec) | No |
| client playback | satellite SDK | 48 kHz (client 16→48 upsample) | No (now correct) |

## Queues / state (existing, unchanged)

- `_out: asyncio.Queue[Optional[bytes]]` (maxsize 100) — now carries canonical
  48 kHz frames; provides backpressure → real-time pacing.
- `_server: asyncio.Queue[Optional[ServerFrame]]` (maxsize 200) — merged outbound
  stream; unchanged.
- `_downsample_state` — `audioop.ratecv` state for 48→16; unchanged, carried
  across frames for seamless output.
- `_seq` — monotonic `AudioChunk` sequence; unchanged.

## Components

- **`decode_tts_to_pcm48k(pcm: bytes) -> bytes`** *(new, neutral helper)* — wraps
  `av.open` + `av.AudioResampler(format="s16", layout="mono", rate=48000)` (ffmpeg,
  in-process). Returns concatenated canonical PCM (empty on empty/undecodable
  input). The single canonical decode used by both transports.
- **`PcmFramer(1920)`** *(reused from `webrtc/media.py`)* — slices canonical PCM
  into 20 ms frames; flushes a zero-padded tail.
- **`GrpcMediaAdapter.send_audio`** *(changed)* — decode → frame → enqueue 48 kHz
  frames into `_out`.
- **`GrpcMediaAdapter.run_outbound_pump` / `stop_playback` / `close` /
  `ui_event_sink`** *(unchanged)*.
