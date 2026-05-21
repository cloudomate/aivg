"""ESPHome plaintext-API wire framing (server-side).

The ESPHome native API frames each protobuf message as::

    \\x00              (1-byte preamble; always 0 for plaintext)
    varuint(len)      (1-5 bytes, payload length)
    varuint(opcode)   (1-5 bytes, message-type number)
    payload           (len bytes; protobuf-serialized message)

This module provides the **server-side** encode + decode helpers.
The client side lives in
:mod:`aioesphomeapi._frame_helper.plain_text`, but its
``APIPlaintextFrameHelper`` is an :class:`asyncio.Protocol` tightly
coupled to the client's connection class — we reuse only the
``MESSAGE_NUMBER_TO_PROTO`` opcode table from
:mod:`aioesphomeapi.core`.

R-1 (feature 017): the proto schemas + opcode assignments live in
:mod:`aioesphomeapi.api_pb2` and :mod:`aioesphomeapi.core` — we never
invent an ESPHome wire format locally. Encoding-of-varints is
re-implemented here (~10 LoC) so the only dependency on
``aioesphomeapi`` is the proto + opcode table (public surface).
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional, Tuple

from aioesphomeapi.core import MESSAGE_NUMBER_TO_PROTO  # tuple[type, ...]

__all__ = [
    "PROTO_TO_OPCODE",
    "encode_message",
    "encode_packet",
    "read_next_message",
    "FramingError",
]


class FramingError(RuntimeError):
    """The peer sent a malformed frame (bad preamble or truncated
    varint). The connection is unrecoverable from this point and
    MUST be closed."""


# Reverse map: proto-message-class → opcode integer. Built once at
# import. The forward map (opcode → class) is
# :data:`aioesphomeapi.core.MESSAGE_NUMBER_TO_PROTO` (a tuple where
# index == opcode).
PROTO_TO_OPCODE: dict[type, int] = {
    cls: idx for idx, cls in enumerate(MESSAGE_NUMBER_TO_PROTO) if cls is not None
}


def _varuint_to_bytes(value: int) -> bytes:
    """Encode an unsigned integer as a protobuf-style varuint."""
    if value <= 0x7F:
        return bytes((value,))
    out = bytearray()
    while value:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
    return bytes(out)


async def _read_varuint(reader: asyncio.StreamReader) -> int:
    """Read one varuint from the stream. Raises :class:`FramingError`
    if the varint exceeds 5 bytes (which would overflow uint32 — the
    ESPHome protocol limit)."""
    result = 0
    shift = 0
    for _ in range(5):
        chunk = await reader.readexactly(1)
        b = chunk[0]
        result |= (b & 0x7F) << shift
        if (b & 0x80) == 0:
            return result
        shift += 7
    raise FramingError("varuint exceeded 5 bytes")


def encode_packet(opcode: int, payload: bytes) -> bytes:
    """Frame one packet for the wire. Used directly when the caller
    already holds a serialized payload (e.g., empty messages). Most
    callers should use :func:`encode_message` instead."""
    return b"\x00" + _varuint_to_bytes(len(payload)) + _varuint_to_bytes(opcode) + payload


def encode_message(msg: Any) -> bytes:
    """Frame one protobuf message for the wire. Looks up the opcode
    via :data:`PROTO_TO_OPCODE`; raises ``KeyError`` if the message
    class is not in the ESPHome opcode table (would indicate a
    aioesphomeapi version skew)."""
    cls = type(msg)
    opcode = PROTO_TO_OPCODE[cls]
    payload = msg.SerializeToString()
    return encode_packet(opcode, payload)


async def read_next_message(
    reader: asyncio.StreamReader,
) -> Tuple[int, Optional[Any]]:
    """Read one full frame from the stream and return
    ``(opcode, message)``.

    - ``message`` is a parsed protobuf instance when the opcode is
      known to our ``MESSAGE_NUMBER_TO_PROTO`` table.
    - ``message`` is ``None`` for unknown opcodes (the caller logs and
      discards — required by the spec's "unknown messages MUST be
      silently dropped" edge case).
    - Raises :class:`FramingError` on a malformed preamble or varint.
    - Raises :class:`asyncio.IncompleteReadError` when the peer closes
      the stream mid-frame (caller treats as EOF).
    """
    preamble_b = await reader.readexactly(1)
    if preamble_b != b"\x00":
        raise FramingError(
            f"invalid preamble {preamble_b!r} (encryption / corrupted stream?)"
        )
    length = await _read_varuint(reader)
    opcode = await _read_varuint(reader)
    payload = await reader.readexactly(length) if length else b""
    proto_cls = (
        MESSAGE_NUMBER_TO_PROTO[opcode]
        if 0 <= opcode < len(MESSAGE_NUMBER_TO_PROTO)
        else None
    )
    if proto_cls is None:
        return opcode, None  # unknown message — caller drops
    msg = proto_cls()
    msg.ParseFromString(payload)
    return opcode, msg
