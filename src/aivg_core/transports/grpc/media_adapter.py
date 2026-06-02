"""``GrpcMediaAdapter`` — the seam between an ``Audio.Stream`` gRPC call
and the canonical :class:`aivg_core.webrtc.session.Session` (feature 021,
research R-3/R-4).

Like ``transports.esphome.media_adapter`` it satisfies the
:class:`MediaTransport` Protocol with two PCM queues and resamples at the
transport boundary (wire 16 kHz ↔ internal 48 kHz) so ``Session`` stays
sample-rate-agnostic. It *additionally* owns a single **outbound
``ServerFrame`` queue** that merges three producers onto one gRPC response
stream (FR-010): synthesized audio (from ``Session.send_audio``), turn
lifecycle events, and streaming transcripts (both from ``Session``'s UI
sink). The servicer simply drains that queue and yields.
"""

from __future__ import annotations

import asyncio
import audioop
from typing import Optional

from ._generated import audio_pb2
from . import codec as _codec

# Wire / internal audio constants (identical to the esphome adapter).
_WIRE_SR = 16000
_INTERNAL_SR = 48000
_FRAME_MS = 20
_INTERNAL_FRAME_BYTES = (_INTERNAL_SR * _FRAME_MS // 1000) * 2  # 1920
_WIRE_FRAME_BYTES = (_WIRE_SR * _FRAME_MS // 1000) * 2          # 640


class GrpcMediaAdapter:
    """Satisfies :class:`aivg_core.webrtc.session.MediaTransport` and bridges
    a single voice session onto one bidi ``Audio.Stream``.

    Queues (all bounded — a slow consumer can never grow memory without
    bound, FR-021):

    - ``_in``     inbound PCM frames, resampled 16 kHz→48 kHz / 20 ms.
    - ``_out``    outbound PCM frames from ``Session.send_audio`` (48 kHz).
    - ``_server`` merged outbound ``ServerFrame`` stream the servicer yields.
    """

    def __init__(self, *, downstream_codec: int) -> None:
        self._codec = downstream_codec
        self._in: asyncio.Queue[Optional[bytes]] = asyncio.Queue(maxsize=100)
        self._out: asyncio.Queue[Optional[bytes]] = asyncio.Queue(maxsize=100)
        self._server: asyncio.Queue[Optional[audio_pb2.ServerFrame]] = asyncio.Queue(
            maxsize=200
        )
        self._state = "connected"
        self._closed = False
        self._upsample_state: Optional[bytes] = None
        self._downsample_state: Optional[bytes] = None
        self._reframe_buf = bytearray()
        self._seq = 0
        self._speaking = False

    # --- MediaTransport Protocol surface --------------------------------

    async def receive(self) -> Optional[bytes]:
        return await self._in.get()

    async def send_audio(self, pcm: bytes) -> None:
        if self._closed:
            return
        await self._out.put(pcm)

    async def stop_playback(self) -> None:
        # Drain queued outbound PCM AND any not-yet-yielded audio frames so
        # barge-in stops playback promptly (mirrors WebRTC/esphome).
        for q in (self._out,):
            try:
                while True:
                    q.get_nowait()
            except asyncio.QueueEmpty:
                pass

    @property
    def connection_state(self) -> str:
        return self._state

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._state = "closed"
        # Wake Session.run()'s pending receive() and end both pumps.
        for q, sentinel in ((self._in, None), (self._out, None)):
            try:
                q.put_nowait(sentinel)
            except asyncio.QueueFull:
                pass

    # --- inbound push hooks (called by the stream handler) --------------

    def push_inbound(self, pcm_s16le_16k: bytes) -> None:
        """Resample a 16 kHz wire frame to 48 kHz, reframe to 20 ms, enqueue
        for ``Session``. Drops on a full queue rather than blocking the gRPC
        read loop (FR-021)."""
        if self._closed or not pcm_s16le_16k:
            return
        upsampled, self._upsample_state = audioop.ratecv(
            pcm_s16le_16k, 2, 1, _WIRE_SR, _INTERNAL_SR, self._upsample_state
        )
        self._reframe_buf.extend(upsampled)
        while len(self._reframe_buf) >= _INTERNAL_FRAME_BYTES:
            frame = bytes(self._reframe_buf[:_INTERNAL_FRAME_BYTES])
            del self._reframe_buf[:_INTERNAL_FRAME_BYTES]
            try:
                self._in.put_nowait(frame)
            except asyncio.QueueFull:
                return

    def push_eof(self) -> None:
        """Flush a trailing partial frame (zero-padded) then signal
        end-of-stream so ``Session``'s collect loop unwinds."""
        if self._reframe_buf and len(self._reframe_buf) < _INTERNAL_FRAME_BYTES:
            self._reframe_buf.extend(b"\x00" * (_INTERNAL_FRAME_BYTES - len(self._reframe_buf)))
            try:
                self._in.put_nowait(bytes(self._reframe_buf))
            except asyncio.QueueFull:
                pass
            self._reframe_buf.clear()
        try:
            self._in.put_nowait(None)
        except asyncio.QueueFull:
            pass

    # --- outbound: PCM pump + UI events -> merged ServerFrame stream -----

    async def run_outbound_pump(self) -> None:
        """Drain outbound PCM, downsample 48 kHz→16 kHz, encode to the chosen
        codec, and enqueue an ``AudioChunk`` ServerFrame. Terminates the
        ServerFrame stream with a ``None`` sentinel when the session closes."""
        try:
            while True:
                chunk = await self._out.get()
                if chunk is None:
                    break
                if not chunk:
                    continue
                downsampled, self._downsample_state = audioop.ratecv(
                    chunk, 2, 1, _INTERNAL_SR, _WIRE_SR, self._downsample_state
                )
                payload = _codec.encode(self._codec, downsampled)
                self._seq += 1
                frame = audio_pb2.ServerFrame(
                    audio=audio_pb2.AudioChunk(
                        codec=self._codec, payload=payload, seq=self._seq
                    )
                )
                await self._server.put(frame)
        finally:
            try:
                self._server.put_nowait(None)
            except asyncio.QueueFull:
                # Last resort: block briefly so the servicer always sees EOS.
                await self._server.put(None)

    def ui_event_sink(self, evt: dict) -> None:
        """Convert a ``Session`` UI event into a ``ServerFrame`` on the same
        stream (FR-010). Best-effort + non-blocking — a UI hiccup must never
        affect the audio path."""
        try:
            kind = evt.get("type")
            frame: Optional[audio_pb2.ServerFrame] = None
            if kind == "state":
                state = evt.get("state")
                if state == "speaking" and not self._speaking:
                    self._speaking = True
                    frame = audio_pb2.ServerFrame(
                        event=audio_pb2.ServerEvent(
                            kind=audio_pb2.ServerEvent.SPEAKING_STARTED
                        )
                    )
                elif state != "speaking" and self._speaking:
                    self._speaking = False
                    frame = audio_pb2.ServerFrame(
                        event=audio_pb2.ServerEvent(
                            kind=audio_pb2.ServerEvent.SPEAKING_ENDED
                        )
                    )
            elif kind == "partial_transcript":
                frame = audio_pb2.ServerFrame(
                    transcript=audio_pb2.Transcript(
                        text=str(evt.get("text", "")), is_final=False
                    )
                )
            if frame is not None:
                self._server.put_nowait(frame)
        except Exception:  # noqa: BLE001 - UI fan-out must never break voice
            pass

    async def next_server_frame(self) -> Optional[audio_pb2.ServerFrame]:
        """The servicer awaits this and yields each frame until ``None``."""
        return await self._server.get()
