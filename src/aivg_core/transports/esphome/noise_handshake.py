"""Noise_NNpsk0_25519_ChaChaPoly_SHA256 handshake for the ESPHome
native API encrypted mode (feature 017 client-mode addition).

ESPHome 2026.1.0 removed plaintext API password — only the encrypted
mode remains. AIVG's client-mode dialer MUST therefore speak Noise
to talk to any modern ESPHome firmware.

This module implements the **initiator** side (we dial out, so we're
the initiator). Server-side noise (accept noise-encrypted inbound)
is a future addition; the OHF-Voice linux-voice-assistant case
still uses plaintext server-side.

Wire format (noise mode, differs from plaintext):

  outbound bytes (after TCP connect):
    NOISE_HELLO marker:  b"\\x01\\x00\\x00"            (3 bytes)
    initial frame:       \\x01 + uint16_be(len) + \\x00 + noise_e
  inbound bytes (from device):
    server-hello frame:  \\x01 + uint16_be(len) + chosen_proto + server_name\\x00
    handshake frame:     \\x01 + uint16_be(len) + \\x00 + noise_ee_es_psk
  after handshake:
    every encrypted frame is  \\x01 + uint16_be(len) + ciphertext
    where ciphertext decrypts to:
      uint16_be(msg_type) + uint16_be(msg_len) + payload

Note: post-handshake frames use **big-endian uint16** for both
length and opcode — NOT the varint encoding used by plaintext mode.
This is an ESPHome-specific detail of the encrypted wire surface.

References:
- aioesphomeapi/_frame_helper/noise.py (the canonical client impl)
- Noise Protocol Framework, Noise_NN handshake variant with psk0
"""

from __future__ import annotations

import asyncio
import binascii
import struct
from functools import partial
from typing import Optional, Tuple

from chacha20poly1305_reuseable import ChaCha20Poly1305Reusable
from noise.backends.default import DefaultNoiseBackend
from noise.backends.default.ciphers import (
    ChaCha20Cipher,
    CryptographyCipher,
)
from noise.connection import NoiseConnection
from noise.state import CipherState

__all__ = [
    "NoiseHandshakeError",
    "NoiseHandshakeClient",
]


# ChaCha20-Poly1305 with a reusable cipher object — mirrors
# aioesphomeapi's ESPHomeNoiseBackend optimization. Decoding /
# encoding many short frames is much cheaper when the cipher object
# isn't reconstructed each call.

_PACK_NONCE = partial(struct.Struct("<LQ").pack, 0)


class _ChaCha20CipherReuseable(ChaCha20Cipher):  # type: ignore[misc]
    format_nonce = staticmethod(_PACK_NONCE)

    @property
    def klass(self):
        return ChaCha20Poly1305Reusable


class _ESPHomeNoiseBackend(DefaultNoiseBackend):  # type: ignore[misc]
    def __init__(self) -> None:
        super().__init__()
        self.ciphers["ChaChaPoly"] = _ChaCha20CipherReuseable


_BACKEND = _ESPHomeNoiseBackend()

NOISE_HELLO = b"\x01\x00\x00"
_NOISE_PROLOGUE = b"NoiseAPIInit\x00\x00"


class NoiseHandshakeError(RuntimeError):
    """The noise handshake failed — bad PSK, MAC failure, or
    malformed frame from peer. The connection is unrecoverable."""


class NoiseHandshakeClient:
    """Initiator side of the Noise_NNpsk0_25519_ChaChaPoly_SHA256
    handshake. Wraps a pair of StreamReader/Writer with encrypted
    send_message / recv_message after handshake completes.

    Usage:

        noise = NoiseHandshakeClient(reader, writer, noise_psk=base64_key)
        await noise.handshake()
        # Now noise.send_message(opcode, payload) and
        # noise.recv_message() use the encrypted frame format.
    """

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        noise_psk: str,
        expected_server_name: Optional[str] = None,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._noise_psk = noise_psk
        self._expected_server_name = expected_server_name
        self.server_name: Optional[str] = None

        # NoiseConnection state machine.
        self._proto = NoiseConnection.from_name(
            b"Noise_NNpsk0_25519_ChaChaPoly_SHA256", backend=_BACKEND,
        )
        self._proto.set_as_initiator()
        self._proto.set_psks(self._decode_psk(noise_psk))
        self._proto.set_prologue(_NOISE_PROLOGUE)
        self._proto.start_handshake()

        # Set after handshake completes.
        self._encrypt_cipher: Optional[_Encrypter] = None
        self._decrypt_cipher: Optional[_Decrypter] = None

    # --- handshake ----------------------------------------------------

    async def handshake(self) -> None:
        """Run the full handshake: send our hello + first noise msg,
        receive server-hello, receive server's handshake response,
        derive cipher state. Raises :class:`NoiseHandshakeError` on
        any deviation from the expected protocol."""
        # 1) Send NOISE_HELLO marker + our initial handshake frame.
        initial_e = self._proto.write_message()
        await self._write_handshake_frame(b"\x00" + initial_e, prepend=NOISE_HELLO)

        # 2) Read server-hello frame: chosen_proto + server_name\0
        hello = await self._read_frame()
        if not hello:
            raise NoiseHandshakeError("server-hello frame is empty")
        chosen_proto = hello[0]
        if chosen_proto != 0x01:
            raise NoiseHandshakeError(
                f"unknown noise protocol selected by server: {chosen_proto:#x}"
            )
        # server_name is a null-terminated string starting at byte 1.
        zero_idx = hello.find(b"\x00", 1)
        if zero_idx != -1:
            self.server_name = hello[1:zero_idx].decode("utf-8", "replace")
            if (
                self._expected_server_name is not None
                and self._expected_server_name != self.server_name
            ):
                raise NoiseHandshakeError(
                    f"server name mismatch: expected "
                    f"{self._expected_server_name!r}, got {self.server_name!r}"
                )

        # 3) Read server's handshake-finish frame: \x00 + noise_response.
        finish = await self._read_frame()
        if not finish or finish[0] != 0x00:
            # First byte != 0x00 means the device sent an error message
            # (typically "Handshake MAC failure" — wrong PSK).
            explanation = (
                finish[1:].decode("utf-8", "replace") if finish else "<empty>"
            )
            raise NoiseHandshakeError(
                f"noise handshake failed: {explanation!r} "
                f"(usually means the PSK is wrong)"
            )
        try:
            self._proto.read_message(finish[1:])
        except Exception as exc:  # noqa: BLE001 - upstream exception types vary
            raise NoiseHandshakeError(f"noise read_message failed: {exc}") from exc

        # 4) Derive cipher state.
        np = self._proto.noise_protocol
        self._encrypt_cipher = _Encrypter(np.cipher_state_encrypt)
        self._decrypt_cipher = _Decrypter(np.cipher_state_decrypt)

    # --- encrypted message I/O ----------------------------------------

    async def send_message(self, opcode: int, payload: bytes) -> None:
        """Send one encrypted message (opcode + payload). Must be
        called only after :meth:`handshake` completed."""
        await self.send_messages([(opcode, payload)])

    async def send_messages(self, messages: list) -> None:
        """Send N encrypted messages **batched into one TCP write**.

        ESPHome firmware (verified against 2026.5.0) drops the
        connection if a Hello is sent without an immediately-
        following Auth in the same TCP packet. aioesphomeapi's
        own client batches them via ``make_noise_packets`` +
        ``_write_bytes`` → one ``transport.write`` call. We mirror
        that here by accumulating all framed ciphertext into one
        buffer and writing once."""
        if self._encrypt_cipher is None:
            raise NoiseHandshakeError("send_messages before handshake")
        out = bytearray()
        for opcode, payload in messages:
            data_len = len(payload)
            inner = struct.pack(">HH", opcode, data_len) + payload
            ciphertext = self._encrypt_cipher.encrypt(inner)
            out.append(0x01)
            out += struct.pack(">H", len(ciphertext))
            out += ciphertext
        self._writer.write(bytes(out))
        await self._writer.drain()

    async def recv_message(self) -> Tuple[int, bytes]:
        """Receive one encrypted message. Returns ``(opcode, payload)``."""
        if self._decrypt_cipher is None:
            raise NoiseHandshakeError("recv_message before handshake")
        frame = await self._read_frame()
        plaintext = self._decrypt_cipher.decrypt(frame)
        if len(plaintext) < 4:
            raise NoiseHandshakeError(
                f"decrypted frame too short ({len(plaintext)} bytes)"
            )
        opcode, _data_len = struct.unpack(">HH", plaintext[:4])
        payload = plaintext[4:]
        return opcode, payload

    # --- raw frame I/O (handshake + post-handshake share format) ------

    async def _write_handshake_frame(
        self, body: bytes, *, prepend: bytes = b""
    ) -> None:
        """Write one wire frame: ``\\x01 + uint16_be(len) + body``,
        with an optional raw ``prepend`` written first (used for
        NOISE_HELLO before the initial handshake frame)."""
        header = b"\x01" + struct.pack(">H", len(body))
        self._writer.write(prepend + header + body)
        await self._writer.drain()

    async def _read_frame(self) -> bytes:
        """Read one ``\\x01 + uint16_be(len) + body`` frame. Raises on
        bad preamble."""
        header = await self._reader.readexactly(3)
        if header[0] != 0x01:
            raise NoiseHandshakeError(
                f"noise frame preamble {header[0]:#x} != 0x01 "
                f"(connection corrupted or peer in wrong mode)"
            )
        length = (header[1] << 8) | header[2]
        return await self._reader.readexactly(length) if length else b""

    # --- PSK decode ---------------------------------------------------

    @staticmethod
    def _decode_psk(psk: str) -> bytes:
        """Decode the base64-encoded PSK. ESPHome's `api: encryption:
        key:` is exactly 32 bytes of base64."""
        try:
            psk_bytes = binascii.a2b_base64(psk)
        except (binascii.Error, ValueError) as exc:
            raise NoiseHandshakeError(
                f"malformed noise PSK (base64 decode failed): {exc}"
            )
        if len(psk_bytes) != 32:
            raise NoiseHandshakeError(
                f"noise PSK must be 32 bytes after base64-decode "
                f"(got {len(psk_bytes)})"
            )
        return psk_bytes


# --- cipher wrappers (mirrors aioesphomeapi.EncryptCipher / DecryptCipher) ---


class _Encrypter:
    """ChaCha20-Poly1305 encrypt wrapper with nonce counter."""

    __slots__ = ("_nonce", "_encrypt")

    def __init__(self, cipher_state: CipherState) -> None:
        crypto: CryptographyCipher = cipher_state.cipher
        cipher: ChaCha20Poly1305Reusable = crypto.cipher
        self._nonce = cipher_state.n
        self._encrypt = cipher.encrypt

    def encrypt(self, data: bytes) -> bytes:
        ct = self._encrypt(_PACK_NONCE(self._nonce), data, None)
        self._nonce += 1
        return ct


class _Decrypter:
    """ChaCha20-Poly1305 decrypt wrapper with nonce counter."""

    __slots__ = ("_nonce", "_decrypt")

    def __init__(self, cipher_state: CipherState) -> None:
        crypto: CryptographyCipher = cipher_state.cipher
        cipher: ChaCha20Poly1305Reusable = crypto.cipher
        self._nonce = cipher_state.n
        self._decrypt = cipher.decrypt

    def decrypt(self, data: bytes) -> bytes:
        pt = self._decrypt(_PACK_NONCE(self._nonce), data, None)
        self._nonce += 1
        return pt
