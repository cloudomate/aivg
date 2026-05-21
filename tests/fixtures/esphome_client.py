"""In-process ESPHome native API client for integration tests.

Speaks the real `aioesphomeapi.api_pb2` proto types via the same
framing helpers the gateway uses (``framing.encode_message`` /
``read_next_message``). Connects via a real TCP socket to an
``EsphomeTransport`` listening on an ephemeral port.

Exposes high-level async methods so a test can:

  client = FakeEsphomeClient("device-1", "secret")
  await client.connect_and_auth(host, port)
  await client.start_voice_pipeline()
  await client.send_audio_pcm16k(pcm)
  events = await client.collect_events_until(Event.RUN_END, timeout=5.0)
  audio = client.captured_audio    # bytes of all VoiceAssistantAudio in
  await client.disconnect()
"""

from __future__ import annotations

import asyncio
from typing import Optional

import aioesphomeapi.api_pb2 as pb

from aivg_core.transports.esphome.framing import encode_message, read_next_message
from aivg_core.transports.esphome.voice_protocol import Event  # noqa: F401 - re-exported


class FakeEsphomeClient:
    """Minimal ESPHome-protocol client speaking the AIVG gateway's
    server side."""

    def __init__(self, device_id: str, api_key: str) -> None:
        self.device_id = device_id
        self.api_key = api_key
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self.events: list[int] = []          # event_type from VoiceAssistantEventResponse
        self.captured_audio: bytearray = bytearray()
        self._reader_task: Optional[asyncio.Task] = None

    async def connect_and_auth(self, host: str, port: int) -> None:
        """Open TCP, run Hello + Connect handshake."""
        self._reader, self._writer = await asyncio.open_connection(host, port)
        # Hello.
        await self._send(pb.HelloRequest(
            client_info=self.device_id,
            api_version_major=1,
            api_version_minor=10,
        ))
        opcode, msg = await read_next_message(self._reader)
        assert isinstance(msg, pb.HelloResponse), f"expected HelloResponse, got {type(msg).__name__}"
        # Auth.
        await self._send(pb.ConnectRequest(password=self.api_key))
        opcode, msg = await read_next_message(self._reader)
        assert isinstance(msg, pb.ConnectResponse), f"expected ConnectResponse, got {type(msg).__name__}"
        if msg.invalid_password:
            raise PermissionError(f"auth failed for device {self.device_id!r}")
        # Subscribe to voice-assistant pipelines.
        await self._send(pb.SubscribeVoiceAssistantRequest(subscribe=True))
        # Start a reader task that collects all subsequent messages
        # in the background.
        self._reader_task = asyncio.create_task(self._reader_loop())

    async def _send(self, msg) -> None:
        assert self._writer is not None
        self._writer.write(encode_message(msg))
        await self._writer.drain()

    async def _reader_loop(self) -> None:
        """Drain incoming messages, classifying them into events +
        captured audio."""
        assert self._reader is not None
        try:
            while True:
                opcode, msg = await read_next_message(self._reader)
                if isinstance(msg, pb.VoiceAssistantEventResponse):
                    self.events.append(msg.event_type)
                elif isinstance(msg, pb.VoiceAssistantAudio):
                    if msg.data:
                        self.captured_audio.extend(msg.data)
                elif isinstance(msg, pb.PingRequest):
                    await self._send(pb.PingResponse())
                # Other messages (VoiceAssistantResponse, etc.) are
                # informational; we ignore them in tests.
        except (asyncio.IncompleteReadError, ConnectionError, asyncio.CancelledError):
            pass

    async def start_voice_pipeline(self) -> None:
        """Send VoiceAssistantRequest(start=True) to begin a pipeline run."""
        await self._send(pb.VoiceAssistantRequest(start=True, conversation_id="test"))

    async def send_audio_pcm16k(self, pcm: bytes, *, end: bool = False) -> None:
        """Send one frame of inbound audio. ``pcm`` is raw PCM16 mono
        @ 16 kHz."""
        await self._send(pb.VoiceAssistantAudio(data=pcm, end=end))

    async def wait_for_event(self, event_type: int, *, timeout: float = 5.0) -> bool:
        """Wait until the client has received ``event_type``. Returns
        True if seen within the timeout."""
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            if event_type in self.events:
                return True
            await asyncio.sleep(0.01)
        return False

    async def disconnect(self) -> None:
        """Close the connection cleanly."""
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._reader_task = None
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except (ConnectionError, OSError):
                pass
        self._writer = None
        self._reader = None
