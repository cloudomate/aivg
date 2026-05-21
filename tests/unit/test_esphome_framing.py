"""Feature 017 — wire-framing unit tests for the ESPHome transport.

Per [contracts/esphome-transport.md § 8](../../specs/017-esphome-voice-transport/contracts/esphome-transport.md#8-contract-tests-binding)
rows 1-2.
"""

from __future__ import annotations

import asyncio
import io

import pytest

# Module-level skip guard: the ESPHome transport only loads when
# aioesphomeapi is on the path (it's a runtime dep added in
# feature 017 / T001). On a stripped CI without the dep, skip cleanly.
pytest.importorskip("aioesphomeapi")
import aioesphomeapi.api_pb2 as pb  # noqa: E402

from aivg_core.transports.esphome.framing import (  # noqa: E402
    FramingError,
    PROTO_TO_OPCODE,
    encode_message,
    encode_packet,
    read_next_message,
)


def _stream_from(data: bytes) -> asyncio.StreamReader:
    """Build a StreamReader pre-loaded with ``data`` (for read_next_message)."""
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()
    return reader


@pytest.mark.asyncio
async def test_varint_roundtrip_hello_request():
    """HelloRequest with a non-trivial client_info encodes + decodes losslessly."""
    msg_in = pb.HelloRequest(client_info="aivg-gateway-test", api_version_major=1, api_version_minor=10)
    wire = encode_message(msg_in)

    # Wire prefix sanity: preamble 0, then length varuint, then opcode varuint.
    assert wire[0] == 0x00
    assert PROTO_TO_OPCODE[pb.HelloRequest] == 0  # known opcode

    reader = _stream_from(wire)
    opcode, msg_out = await read_next_message(reader)
    assert opcode == 0
    assert isinstance(msg_out, pb.HelloRequest)
    assert msg_out.client_info == "aivg-gateway-test"
    assert msg_out.api_version_major == 1
    assert msg_out.api_version_minor == 10


@pytest.mark.asyncio
async def test_varint_roundtrip_voice_assistant_audio():
    """VoiceAssistantAudio with a 640-byte PCM payload roundtrips."""
    pcm = b"\x12\x34" * 320  # 320 samples = 20 ms @ 16 kHz
    msg_in = pb.VoiceAssistantAudio(data=pcm, end=False)
    wire = encode_message(msg_in)

    reader = _stream_from(wire)
    opcode, msg_out = await read_next_message(reader)
    assert opcode == PROTO_TO_OPCODE[pb.VoiceAssistantAudio]  # 105
    assert isinstance(msg_out, pb.VoiceAssistantAudio)
    assert msg_out.data == pcm
    assert msg_out.end is False


@pytest.mark.asyncio
async def test_varint_roundtrip_voice_assistant_request():
    """VoiceAssistantRequest with start=True roundtrips."""
    msg_in = pb.VoiceAssistantRequest(start=True, conversation_id="conv-1")
    wire = encode_message(msg_in)
    reader = _stream_from(wire)
    opcode, msg_out = await read_next_message(reader)
    assert opcode == PROTO_TO_OPCODE[pb.VoiceAssistantRequest]
    assert msg_out.start is True
    assert msg_out.conversation_id == "conv-1"


@pytest.mark.asyncio
async def test_unknown_opcode_returns_none():
    """Unknown opcodes MUST yield ``message is None`` (caller drops)."""
    # Forge a frame with opcode 9999 (well past the table). The reader
    # MUST still consume the bytes and return a result rather than crash.
    wire = encode_packet(9999, b"\x00\x01\x02")
    reader = _stream_from(wire)
    opcode, msg = await read_next_message(reader)
    assert opcode == 9999
    assert msg is None  # unknown → drop


@pytest.mark.asyncio
async def test_invalid_preamble_raises_framing_error():
    """A non-zero preamble (e.g., encrypted-API magic 0x01) raises."""
    wire = b"\x01" + b"\x00\x00"  # 0x01 preamble + empty msg
    reader = _stream_from(wire)
    with pytest.raises(FramingError):
        await read_next_message(reader)


@pytest.mark.asyncio
async def test_varuint_overflow_raises():
    """A varuint that doesn't terminate within 5 bytes raises."""
    # 5 bytes each with continuation bit set → varuint > uint32 limit
    wire = b"\x00" + b"\xff\xff\xff\xff\xff"
    reader = _stream_from(wire)
    with pytest.raises(FramingError):
        await read_next_message(reader)


@pytest.mark.asyncio
async def test_two_frames_back_to_back():
    """Two consecutive frames in one buffer decode independently."""
    a = pb.PingRequest()
    b = pb.PingResponse()
    wire = encode_message(a) + encode_message(b)
    reader = _stream_from(wire)
    op_a, msg_a = await read_next_message(reader)
    op_b, msg_b = await read_next_message(reader)
    assert isinstance(msg_a, pb.PingRequest)
    assert isinstance(msg_b, pb.PingResponse)
    assert op_a == PROTO_TO_OPCODE[pb.PingRequest]
    assert op_b == PROTO_TO_OPCODE[pb.PingResponse]
