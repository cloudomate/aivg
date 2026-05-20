"""Improv-over-BLE central (feature 011 T049, R-2).

Speaks the Improv-Wifi GATT service (https://www.improv-wifi.com/ble/) from
the operator's BLE-capable host to a freshly-flashed satellite device. The
pure framing functions below have **no BLE dependency** so the GATT
protocol can be unit-tested against a mock peripheral; the
:class:`ImprovBleClient` wrapper uses :mod:`bleak` lazily (it's the
``[ble]`` extra; absent imports surface as
``error.code = "ble_unavailable"`` rather than a Python import error).

Stable ``error.code`` set this module raises (consumed by exit_codes.py):

* ``ble_unavailable`` — ``bleak`` not installed or no BLE adapter found.
* ``improv_timeout`` — peripheral not discovered or state didn't advance.
* ``wifi_join_failed`` — peripheral reported error state 0x03
  (UNABLE_TO_PROVISION) — typically wrong password or out of range.
* ``ble_provisioning_failed`` — anything else (auth required, unknown RPC,
  invalid packet).
"""

from __future__ import annotations

import asyncio
import enum
from dataclasses import dataclass
from typing import Iterable, Optional

# --- GATT identifiers (from improv-wifi.com/ble) -------------------------

SERVICE_UUID = "00467768-6228-2272-4663-277478268000"
CHAR_CAPABILITIES = "00467768-6228-2272-4663-277478268001"
CHAR_CURRENT_STATE = "00467768-6228-2272-4663-277478268002"
CHAR_ERROR_STATE = "00467768-6228-2272-4663-277478268003"
CHAR_RPC_COMMAND = "00467768-6228-2272-4663-277478268004"
CHAR_RPC_RESULT = "00467768-6228-2272-4663-277478268005"


class ImprovState(enum.IntEnum):
    AUTHORIZATION_REQUIRED = 0x01
    AUTHORIZED = 0x02
    PROVISIONING = 0x03
    PROVISIONED = 0x04


class ImprovError(enum.IntEnum):
    NO_ERROR = 0x00
    INVALID_RPC_PACKET = 0x01
    UNKNOWN_RPC_COMMAND = 0x02
    UNABLE_TO_PROVISION = 0x03  # wrong Wi-Fi password / out of range
    NOT_AUTHORIZED = 0x04
    UNKNOWN_ERROR = 0xFF


class ImprovRpcCommand(enum.IntEnum):
    SEND_WIFI_SETTINGS = 0x01
    IDENTIFY = 0x02
    GET_CURRENT_STATE = 0x03
    GET_DEVICE_INFO = 0x04
    GET_WIFI_NETWORKS = 0x05


# --- typed local exceptions (mapped to error.code by aivg_cli) -------------


class ImprovError_(Exception):
    """Base — carries a stable string code for envelope mapping."""

    code = "ble_provisioning_failed"


class BleUnavailable(ImprovError_):
    code = "ble_unavailable"


class ImprovTimeout(ImprovError_):
    code = "improv_timeout"


class WifiJoinFailed(ImprovError_):
    code = "wifi_join_failed"


# --- pure framing (no BLE dep — testable) ---------------------------------


def _checksum(data: Iterable[int]) -> int:
    return sum(data) & 0xFF


def encode_rpc_command(command: int, data: bytes = b"") -> bytes:
    """Frame: ``[command][data_length][data...][checksum]``.

    ``checksum`` is the 8-bit sum of every preceding byte.
    """
    if not 0 <= command <= 0xFF:
        raise ValueError(f"command out of range: {command}")
    if len(data) > 0xFF:
        raise ValueError(f"data too long ({len(data)} > 255)")
    body = bytes([command, len(data)]) + data
    return body + bytes([_checksum(body)])


def encode_send_wifi_settings(ssid: str, password: str) -> bytes:
    """RPC payload: length-prefixed SSID followed by length-prefixed password."""
    ssid_b = ssid.encode("utf-8")
    pwd_b = password.encode("utf-8")
    if len(ssid_b) > 0xFF or len(pwd_b) > 0xFF:
        raise ValueError("ssid/password too long for Improv (>255 bytes)")
    data = bytes([len(ssid_b)]) + ssid_b + bytes([len(pwd_b)]) + pwd_b
    return encode_rpc_command(ImprovRpcCommand.SEND_WIFI_SETTINGS, data)


def decode_rpc_result(frame: bytes) -> tuple[int, list[bytes]]:
    """Parse ``[command][data_length][data...][checksum]``.

    The data segment is a sequence of length-prefixed entries (e.g. a
    provisioned device returns one URL entry per supported endpoint).
    Returns ``(command_echo, [entry_bytes, ...])`` or raises
    :class:`ImprovError_` on framing / checksum failure.
    """
    if len(frame) < 3:
        raise ImprovError_("RPC result too short")
    command = frame[0]
    data_len = frame[1]
    if len(frame) != 2 + data_len + 1:
        raise ImprovError_(
            f"RPC result length mismatch: header says {data_len}, "
            f"frame has {len(frame) - 3} data bytes"
        )
    body = frame[: 2 + data_len]
    if _checksum(body) != frame[-1]:
        raise ImprovError_("RPC result checksum mismatch")
    entries: list[bytes] = []
    data = frame[2 : 2 + data_len]
    i = 0
    while i < len(data):
        entry_len = data[i]
        i += 1
        if i + entry_len > len(data):
            raise ImprovError_("RPC result entry overflows data segment")
        entries.append(data[i : i + entry_len])
        i += entry_len
    return command, entries


def decode_state(b: int) -> ImprovState:
    try:
        return ImprovState(b)
    except ValueError as e:
        raise ImprovError_(f"unknown Improv state byte 0x{b:02x}") from e


def decode_error(b: int) -> ImprovError:
    try:
        return ImprovError(b)
    except ValueError:
        return ImprovError.UNKNOWN_ERROR


def map_error_state(err: ImprovError) -> Optional[type[ImprovError_]]:
    """Decide which exception class an error state implies; ``None`` for
    the no-error case so the caller proceeds."""
    if err == ImprovError.NO_ERROR:
        return None
    if err == ImprovError.UNABLE_TO_PROVISION:
        return WifiJoinFailed
    return ImprovError_


# --- BLE central (bleak; lazy import) ------------------------------------


@dataclass
class ImprovPeer:
    address: str
    name: Optional[str] = None
    rssi: Optional[int] = None


class ImprovBleClient:
    """Thin BLE central; one peripheral at a time. Use as an async-context-
    manager to ensure ``disconnect`` runs even on cancellation.

    Construction does NOT touch the BLE stack; the first :meth:`scan`
    call lazy-imports :mod:`bleak` and raises :class:`BleUnavailable` if
    the import fails (host has no BLE / extra not installed).
    """

    def __init__(self, *, scan_timeout: float = 30.0, op_timeout: float = 30.0) -> None:
        self._scan_timeout = scan_timeout
        self._op_timeout = op_timeout
        self._client = None  # set on connect()
        self._state: ImprovState | None = None
        self._error: ImprovError | None = None
        self._result_frames: asyncio.Queue[bytes] = asyncio.Queue()

    @staticmethod
    def _import_bleak():
        try:
            import bleak  # noqa: F401
            from bleak import BleakClient, BleakScanner  # noqa: F401

            return bleak, BleakClient, BleakScanner
        except Exception as e:  # noqa: BLE001 - any import failure surfaces as BleUnavailable
            raise BleUnavailable(f"bleak unavailable: {e}") from e

    async def scan(self) -> ImprovPeer:
        """Discover one Improv-advertising peripheral within the timeout."""
        _, _, BleakScanner = self._import_bleak()

        try:
            devs = await BleakScanner.discover(
                timeout=self._scan_timeout, return_adv=True, service_uuids=[SERVICE_UUID]
            )
        except Exception as e:  # noqa: BLE001
            raise BleUnavailable(f"scan failed: {e}") from e
        # `devs` is dict[address] = (BLEDevice, AdvertisementData) in newer bleak;
        # fall back to a tuple iteration for older versions.
        for entry in (devs.values() if hasattr(devs, "values") else devs):
            try:
                device, adv = entry
            except (TypeError, ValueError):
                device = entry
                adv = None
            if adv is not None and SERVICE_UUID.lower() not in [
                s.lower() for s in (adv.service_uuids or [])
            ]:
                continue
            return ImprovPeer(
                address=device.address,
                name=getattr(device, "name", None),
                rssi=getattr(adv, "rssi", None) if adv else None,
            )
        raise ImprovTimeout(
            f"no Improv peripheral seen within {self._scan_timeout:.0f}s"
        )

    async def connect(self, peer: ImprovPeer) -> None:
        _, BleakClient, _ = self._import_bleak()
        try:
            self._client = BleakClient(peer.address, timeout=self._op_timeout)
            await self._client.connect()
        except Exception as e:  # noqa: BLE001
            raise BleUnavailable(f"connect failed: {e}") from e

        def _on_state(_h, data: bytearray) -> None:
            if data:
                self._state = decode_state(data[0])

        def _on_error(_h, data: bytearray) -> None:
            if data:
                self._error = decode_error(data[0])

        def _on_result(_h, data: bytearray) -> None:
            self._result_frames.put_nowait(bytes(data))

        try:
            await self._client.start_notify(CHAR_CURRENT_STATE, _on_state)
            await self._client.start_notify(CHAR_ERROR_STATE, _on_error)
            await self._client.start_notify(CHAR_RPC_RESULT, _on_result)
        except Exception as e:  # noqa: BLE001
            raise ImprovError_(f"could not subscribe to Improv chars: {e}") from e

        # Seed state with a one-shot read in case the peripheral does not
        # immediately notify after subscription.
        try:
            raw = await self._client.read_gatt_char(CHAR_CURRENT_STATE)
            if raw:
                self._state = decode_state(raw[0])
        except Exception:  # noqa: BLE001
            pass

    async def send_wifi(self, ssid: str, password: str) -> list[str]:
        """Send credentials, wait for ``PROVISIONED`` state, and return
        the list of URLs the device advertised back (typically its
        management endpoint).
        """
        if self._client is None:
            raise ImprovError_("not connected")
        payload = encode_send_wifi_settings(ssid, password)
        try:
            await self._client.write_gatt_char(CHAR_RPC_COMMAND, payload, response=True)
        except Exception as e:  # noqa: BLE001
            raise ImprovError_(f"write_gatt_char failed: {e}") from e

        await self.wait_for_state(ImprovState.PROVISIONED)

        # Drain any result frames and return URLs.
        urls: list[str] = []
        while not self._result_frames.empty():
            frame = self._result_frames.get_nowait()
            try:
                _cmd, entries = decode_rpc_result(frame)
            except ImprovError_:
                continue
            urls.extend(e.decode("utf-8", errors="replace") for e in entries)
        return urls

    async def wait_for_state(self, target: ImprovState, *, timeout: float | None = None) -> None:
        """Poll the cached notify state until ``target`` is reached (or
        an error state surfaces). Implementations of Improv vary in how
        chatty their notifies are; a small busy loop is robust."""
        deadline = asyncio.get_event_loop().time() + (timeout or self._op_timeout)
        while asyncio.get_event_loop().time() < deadline:
            if self._error and self._error != ImprovError.NO_ERROR:
                exc_cls = map_error_state(self._error)
                if exc_cls is WifiJoinFailed:
                    raise WifiJoinFailed(f"Wi-Fi join failed (error 0x{int(self._error):02x})")
                if exc_cls is not None:
                    raise exc_cls(f"Improv error 0x{int(self._error):02x}")
            if self._state == target:
                return
            await asyncio.sleep(0.1)
        raise ImprovTimeout(
            f"Improv state never reached {target.name} within {timeout or self._op_timeout:.0f}s"
        )

    async def __aenter__(self) -> "ImprovBleClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.disconnect()

    async def disconnect(self) -> None:
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:  # noqa: BLE001 - already-disconnected is fine
                pass
            self._client = None
