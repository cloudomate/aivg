# Research: gRPC downstream TTS decode to canonical 48 kHz PCM

Feature `023-grpc-tts-pcm-decode`. All Technical-Context unknowns resolved; no
open `NEEDS CLARIFICATION`.

## Decision 1 — Decode/resample engine: PyAV (in-process ffmpeg), not a hand-rolled codec and not the ffmpeg CLI

**Decision**: Use **PyAV** (`av.open` to demux/decode + `av.AudioResampler(format="s16",
layout="mono", rate=48000)` to resample/downmix), exactly as
`webrtc/signaling.py:send_audio` already does. PyAV is a thin Python binding over
ffmpeg's libraries (libavformat / libavcodec / libswresample), so **ffmpeg does
all the container parsing, codec decode, channel downmix, and sample-rate
conversion**. We hand-engineer none of that.

**Rationale**:
- **It *is* "reuse ffmpeg".** `av.open` + `av.AudioResampler` delegate entirely to
  ffmpeg's C libraries in-process. The container/codec/rate matrix (WAV, MP3,
  Opus, 22.05/24/44.1/48 kHz, stereo→mono) is handled by ffmpeg, not by us.
- **Parity with WebRTC (FR-003).** The WebRTC transport already normalizes TTS
  this exact way and is proven in production. Using the same engine guarantees the
  two transports produce identical canonical PCM and cannot diverge in codec
  support — which is the precise root cause of this bug.
- **Already a dependency.** `av>=11` is declared in `pyproject.toml`; no new
  third-party dependency, no new system package beyond what WebRTC already needs.
- **In-process & streamable.** Decoding frame-by-frame lets us enqueue 20 ms
  frames into a bounded queue and get natural real-time backpressure (pacing +
  barge-in granularity) without spawning a process per clip.

**Alternatives considered**:
- **ffmpeg CLI subprocess** (`ffmpeg -i pipe:0 -f s16le -ar 48000 -ac 1 pipe:1`):
  also "reuses ffmpeg," but spawns a process **per TTS clip** (fd/zombie
  management, startup latency on every reply, blocking the event loop unless
  driven via `asyncio.create_subprocess_exec`), and **diverges** from the proven
  WebRTC in-process path. Rejected: same ffmpeg work, strictly more operational
  cost and a second, different code path to maintain. (PyAV gives the identical
  ffmpeg result with lower overhead and WebRTC parity.)
- **Hand-rolled decode/resample** (custom WAV parser + polyphase resampler):
  rejected outright — reinvents what ffmpeg already does correctly, is the kind of
  "hand engineering" the user explicitly wants to avoid, and would not match
  WebRTC's behavior.

**Note on the only non-ffmpeg byte handling**: framing into 20 ms chunks
(`PcmFramer`, a ~10-line buffer/slicer — not signal processing) and the *existing*
48 kHz→16 kHz `audioop.ratecv` downsample on the wire side. Neither is part of the
decode; the downsample already exists and is unchanged by this feature.

## Decision 2 — Where the decode runs: in `send_audio`, leaving `run_outbound_pump` unchanged

**Decision**: Decode + resample inside `GrpcMediaAdapter.send_audio(pcm)` and
enqueue real 48 kHz s16 mono PCM frames into `_out`. `run_outbound_pump` keeps its
current job (drain `_out` → 48→16 `audioop.ratecv` downsample → codec encode →
`AudioChunk` `ServerFrame`).

**Rationale**: Matches the originating report ("Once `self._out` holds real 48 kHz
PCM, the existing 48→16 downsample + the client's 16→48 upsample are both
correct"). It makes the `_out` docstring ("outbound PCM frames … (48 kHz)") *true*
instead of aspirational, and keeps the change to a single method plus a shared
helper. The downstream resamplers (gateway and client) are correct by construction
once their input is genuinely 48 kHz PCM.

**Alternatives considered**: Decode inside `run_outbound_pump` instead. Rejected:
it mixes "what format is in the queue" responsibilities, and the queue would still
nominally hold raw bytes — leaving the `_out` contract a lie and making
`stop_playback` (which drains `_out`) operate on undecoded data.

## Decision 3 — Frame to 20 ms before queuing (reuse `PcmFramer`)

**Decision**: Decode frame-by-frame, resample, push through `PcmFramer(1920)`
(20 ms @ 48 kHz s16 mono = 1920 bytes), and `await self._out.put(frame)` per
frame; flush the tail (zero-padded) at clip end. Reuse the existing `PcmFramer`
from `aivg_core.webrtc.media`.

**Rationale**: Mirrors WebRTC's framer + bounded-queue design. Per-frame enqueue
on a bounded `_out` (maxsize 100 ≈ 2 s) gives end-to-end backpressure: the gRPC
servicer yields at the client's real-time read pace → `_server` fills → the pump
blocks → `_out` fills → `send_audio` blocks. That keeps `session.py` in SPEAKING
for the real playback duration (barge-in watcher stays live) and gives `stop_playback`
(which drains `_out`) frame-level interruption granularity. `audioop.ratecv` in the
pump carries `_downsample_state` across frames, so per-frame downsampling is
seamless (no clicks).

**Alternatives considered**: Enqueue the whole decoded clip as one big blob.
Rejected: coarser barge-in (per-clip, not per-frame), weaker pacing, and one
giant `AudioChunk` instead of streamed frames. Framing is low-cost and strictly
better; it also reuses proven code.

## Decision 4 — Empty / sentinel / undecodable handling = WebRTC parity

**Decision**: Reproduce WebRTC's guards: treat empty or `len(pcm) < 16` as
"emit nothing" (covers sentinels like `b"__PROVIDERS_UNAVAILABLE__"`); on
`av.open` failure, drop and keep the session alive; on a mid-clip decode
exception, deliver what was decoded and never raise out of `send_audio`.

**Rationale**: FR-005/006/007 require exactly this, and the WebRTC transport's
field-proven behavior is the reference (FR-003). Raw-PCM input (no container)
falls into the `av.open`-fails → drop path — which is why the existing unit test
that fed raw PCM must be updated to feed a real container.

**Alternatives considered**: Special-casing raw-PCM input so it bypasses `av.open`.
Rejected: WebRTC doesn't do it, real providers return containers, and it would
re-introduce a divergence between the transports.

## Decision 5 — One canonical decode home to prevent recurrence

**Decision**: Lift the decode-to-48 kHz logic into a single neutral helper
(`src/aivg_core/audio/tts_decode.py`, e.g. `decode_tts_to_pcm48k(pcm) -> bytes`).
The gRPC adapter consumes it now; `webrtc/signaling.py:send_audio` is refactored
to consume it too (guarded by the existing WebRTC tests). `PcmFramer` stays in
`webrtc/media.py`.

**Rationale**: This bug exists *because* the gRPC transport hand-copied the
"queue bytes" shape without the WebRTC decode step — i.e. the two transports
diverged. A single shared decoder is the structural fix that stops the divergence
from recurring and satisfies FR-003 by construction.

**Alternatives considered**: Duplicate the decode logic inside the gRPC adapter.
Rejected: it re-creates exactly the divergence that caused this bug. The WebRTC
refactor is kept independently testable so consolidating it carries minimal
regression risk; if the WebRTC refactor is deferred, the shared helper still lands
and gRPC uses it.

## Resolved Technical Context

| Item | Resolution |
|------|------------|
| Decode/resample engine | PyAV (in-process ffmpeg) — `av.open` + `av.AudioResampler` |
| New dependencies | None (`av>=11`, `audioop`, `PcmFramer`, `grpcio` all present) |
| Canonical internal format | s16le mono PCM @ 48 kHz (matches WebRTC + pipeline) |
| Wire format (unchanged) | 16 kHz downstream, existing `Audio.Stream` schema |
| Files touched | `transports/grpc/media_adapter.py`, new `audio/tts_decode.py`, (opt) `webrtc/signaling.py`; tests |
| Test strategy | pytest/pytest-asyncio unit + integration; Principle V end-to-end gate |
