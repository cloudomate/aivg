# Phase 1 Data Model: Real WebRTC Media Transport

This feature adds **no persisted data** and **no new shared models**. The
feature-001 entities (`VoiceSession`, `ConversationTurn`, `SatelliteState`,
`SatelliteConfig`, `LogEntry`) and the `MediaTransport` Protocol are reused
**byte-unchanged** (FR-003/FR-008/FR-012). The entities below are transport-
internal runtime objects only.

## Entity: `AiortcTransport` (implements `session.MediaTransport`)

The real backer for the existing Protocol. Fields are runtime handles, not
stored state.

| Field | Type | Purpose |
|-------|------|---------|
| `_pc` | `aiortc.RTCPeerConnection` | the negotiated voice peer (answerer) |
| `_in_track` | `MediaStreamTrack` (audio, remote) | caller's inbound Opus |
| `_resampler_in` | `av.AudioResampler` → s16/mono/48k | inbound format reconcile |
| `_framer` | `media.PcmFramer` | uniform 20 ms inbound frames |
| `_out_track` | custom `MediaStreamTrack` | outbound Opus to the peer |
| `_out_q` | `asyncio.Queue[bytes]` | 20 ms outbound PCM frames pending |
| `_flushed` | `asyncio.Event`/flag | set by `stop_playback()` for barge-in |
| `_closed` | `bool` | idempotent close guard |

**Behaviour contract** (maps 1:1 to `MediaTransport`):

- `receive() -> Optional[bytes]`: pull → resample → frame; return the next
  1920-byte (20 ms s16le mono 48 kHz) frame; return `None` when the inbound
  track ends or the PC is failed/closed.
- `send_audio(pcm: bytes) -> None`: `av`-decode arbitrary container/rate →
  resample 48 kHz mono s16 → enqueue frames. Undecodable/sentinel/empty input
  is logged and dropped (never raises). At most one clip's frames buffered.
- `stop_playback() -> None`: drain `_out_q`, set `_flushed`; outbound track
  emits silence until the next `send_audio`. Completes well under 300 ms.
- `connection_state -> str`: passthrough of `_pc.connectionState`.
- `close() -> None`: idempotent; stop tracks, cancel internal reader,
  `await _pc.close()`; no orphaned tasks.

## Entity: `PcmFramer` (new, stdlib only — `media.py`)

Pure byte reshaping. **Explicitly not a VAD/endpoint detector**
(constitution I — endpointing stays in `HermesBridge`).

| Field | Type | Purpose |
|-------|------|---------|
| `frame_bytes` | `int` | target frame size (1920 for 20 ms s16 mono 48k) |
| `_buf` | `bytearray` | carry-over remainder between pushes |

| Method | Signature | Rule |
|--------|-----------|------|
| `push` | `push(data: bytes) -> list[bytes]` | append to `_buf`; yield every complete `frame_bytes` slice; keep the remainder |
| `flush` | `flush() -> Optional[bytes]` | if remainder non-empty, right-pad with `\x00` silence to one full frame and return it; else `None` |

Validation rules:

- `frame_bytes` MUST be even (s16 sample alignment) and > 0.
- `push` never returns a partial frame; partials persist in `_buf`.
- `flush` pads with zero bytes (digital silence) only — no synthesized tone
  (constitution I: the transport must not generate audio content).

## State / lifecycle (reused, unchanged)

The conversation state machine and barge-in/teardown transitions live in
`session.py` (`idle → listening → thinking → speaking → listening`;
`speaking → listening` on barge-in; `any → error → teardown/re-offer → idle`)
and are **not modified**. `AiortcTransport` only supplies the audio those
transitions act on; `connection_state` is surfaced into
`VoiceSession.webrtc_state` exactly as the fake transport already does.

## Connection-state mapping

| `RTCPeerConnection.connectionState` | Exposed `connection_state` | Session effect (existing) |
|---|---|---|
| `new`/`connecting` | same string | session opens, awaits media |
| `connected` | `"connected"` | normal flow |
| `disconnected` | `"disconnected"` | transient; media may resume |
| `failed`/`closed` | same string | `receive()→None` → loop ends → `close()` |
