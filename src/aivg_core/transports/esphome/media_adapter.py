"""``EsphomeMediaTransport`` — the seam between the ESPHome connection
and the existing :class:`aivg_core.webrtc.session.Session`.

Feature 017 / R-3 (constitutional Principle IV): the per-turn state
machine (`idle → listening → thinking → speaking`) lives in one
place — ``webrtc/session.py``'s ``Session`` class — and is reused
verbatim across transports. The ESPHome connection adapts itself to
the existing :class:`MediaTransport` Protocol via this class, so no
``Session`` edits are part of this feature.

Sample-rate boundary: ESPHome's voice satellite ships PCM16 mono @
**16 kHz** on the wire (Home Assistant voice-pipeline default).
The existing AIVG voice pipeline runs at **48 kHz** internally
(see `webrtc/signaling._SR`). We resample at the transport boundary
using :func:`audioop.ratecv` (stdlib) so ``Session`` stays
sample-rate-agnostic and matches how the WebRTC ``AiortcTransport``
already resamples (Opus 48 kHz → s16 mono 48 kHz).
"""

from __future__ import annotations

import asyncio
import audioop
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .connection import EsphomeConnection

# Wire / internal audio constants matching the existing pipeline.
_WIRE_SR = 16000     # ESPHome voice satellite wire (Home Assistant default).
_INTERNAL_SR = 48000  # AIVG internal pipeline (`webrtc/signaling._SR`).
_FRAME_MS = 20
_INTERNAL_SAMPLES_PER_FRAME = _INTERNAL_SR * _FRAME_MS // 1000  # 960
_INTERNAL_FRAME_BYTES = _INTERNAL_SAMPLES_PER_FRAME * 2          # 1920
_WIRE_SAMPLES_PER_FRAME = _WIRE_SR * _FRAME_MS // 1000           # 320
_WIRE_FRAME_BYTES = _WIRE_SAMPLES_PER_FRAME * 2                  # 640


class EsphomeMediaTransport:
    """Satisfies :class:`aivg_core.webrtc.session.MediaTransport`.

    Backed by two ``asyncio.Queue`` instances:

    - ``_in``  — inbound PCM frames from the device, resampled to
      48 kHz mono PCM16 and reframed to 20 ms / 1920-byte chunks
      (matches `webrtc/session.py` expectations).
    - ``_out`` — outbound PCM frames from ``Session.send_audio``,
      consumed by the :class:`EsphomeConnection`'s outbound writer
      task and downsampled to 16 kHz before wrapping in
      ``VoiceAssistantAudio`` messages.
    """

    def __init__(self, connection: "EsphomeConnection") -> None:
        self._conn = connection
        # Bounded so a stuck consumer (Session) can't grow memory
        # without bound; 100 frames = 2 s of audio buffered.
        self._in: asyncio.Queue[Optional[bytes]] = asyncio.Queue(maxsize=100)
        self._out: asyncio.Queue[Optional[bytes]] = asyncio.Queue(maxsize=100)
        self._state = "connected"
        self._closed = False
        # Resampler state — both directions need to preserve
        # phase across successive frames.
        self._upsample_state: Optional[bytes] = None  # 16k → 48k
        self._downsample_state: Optional[bytes] = None  # 48k → 16k
        # Reframing buffer: leftover bytes from a 16k → 48k conversion
        # that didn't align to a 20 ms / 1920-byte internal frame.
        self._reframe_buf: bytearray = bytearray()

    # --- MediaTransport Protocol surface (verbatim from webrtc/session.py) ---

    async def receive(self) -> Optional[bytes]:
        return await self._in.get()

    async def send_audio(self, pcm: bytes) -> None:
        if self._closed:
            return
        await self._out.put(pcm)

    async def stop_playback(self) -> None:
        # Drain the outbound queue without sending. Mirrors WebRTC's
        # AiortcTransport.stop_playback for barge-in (C5).
        try:
            while True:
                self._out.get_nowait()
        except asyncio.QueueEmpty:
            pass

    @property
    def connection_state(self) -> str:
        return self._state

    async def close(self) -> None:
        if self._closed:
            return  # idempotent (C7)
        self._closed = True
        self._state = "closed"
        # Wake up Session.run()'s pending receive() so it can exit.
        self._in.put_nowait(None)
        self._out.put_nowait(None)

    # --- ESPHome-side push hooks (called by EsphomeConnection) -------------

    def push_inbound(self, esphome_audio_payload: bytes) -> None:
        """Called when a ``VoiceAssistantAudio`` frame arrives from the
        device. Resamples 16 kHz → 48 kHz and reframes to 20 ms (1920
        byte) chunks matching the existing webrtc pipeline. Drops
        silently if the queue is full (Session has stalled — protects
        against unbounded buffering)."""
        if self._closed or not esphome_audio_payload:
            return
        upsampled, self._upsample_state = audioop.ratecv(
            esphome_audio_payload, 2, 1, _WIRE_SR, _INTERNAL_SR, self._upsample_state
        )
        self._reframe_buf.extend(upsampled)
        # Emit complete 20 ms frames.
        while len(self._reframe_buf) >= _INTERNAL_FRAME_BYTES:
            frame = bytes(self._reframe_buf[:_INTERNAL_FRAME_BYTES])
            del self._reframe_buf[:_INTERNAL_FRAME_BYTES]
            try:
                self._in.put_nowait(frame)
            except asyncio.QueueFull:
                # Consumer stalled; drop the frame rather than block
                # the network read loop. Logged at WARN by the caller.
                return

    def push_eof(self) -> None:
        """Called when the device's audio stream ends (a
        ``VoiceAssistantAudio`` frame with ``end=True``, OR the
        connection closes). Signals Session that the utterance is
        complete so its barge-in / state-machine path can unwind."""
        # Flush any remaining reframe buffer with zero-padding so the
        # platform's endpoint detector sees a clean tail.
        if self._reframe_buf and len(self._reframe_buf) < _INTERNAL_FRAME_BYTES:
            pad = _INTERNAL_FRAME_BYTES - len(self._reframe_buf)
            self._reframe_buf.extend(b"\x00" * pad)
            try:
                self._in.put_nowait(bytes(self._reframe_buf))
            except asyncio.QueueFull:
                pass
            self._reframe_buf.clear()
        # Signal end-of-stream.
        try:
            self._in.put_nowait(None)
        except asyncio.QueueFull:
            pass

    async def drain_outbound(self) -> Optional[bytes]:
        """Pull the next 16 kHz mono PCM chunk to wrap in a
        ``VoiceAssistantAudio`` outbound message. Returns ``None``
        when the transport is closing — the caller's writer loop
        treats that as end-of-stream and stops.

        Internally downsamples 48 kHz → 16 kHz across calls,
        preserving resampler phase via :attr:`_downsample_state`."""
        chunk = await self._out.get()
        if chunk is None:
            return None
        downsampled, self._downsample_state = audioop.ratecv(
            chunk, 2, 1, _INTERNAL_SR, _WIRE_SR, self._downsample_state
        )
        return downsampled
