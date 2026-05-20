"""Unit: Improv-Wifi GATT framing (feature 011 T041, R-2).

Tests the pure functions — no BLE/bleak required. The end-to-end BLE
flow is covered by the (mocked-bleak) integration test in T042.
"""

from __future__ import annotations

import pytest

from aivg_cli.onboard.improv_ble import (
    BleUnavailable,
    ImprovError,
    ImprovError_,
    ImprovRpcCommand,
    ImprovState,
    WifiJoinFailed,
    decode_error,
    decode_rpc_result,
    decode_state,
    encode_rpc_command,
    encode_send_wifi_settings,
    map_error_state,
    _checksum,
)


# --- checksum ------------------------------------------------------------

def test_checksum_basic():
    assert _checksum(b"\x01\x02\x03") == 6
    assert _checksum(b"\xff\xff") == 0xFE  # 0x01FE & 0xFF


# --- encode_rpc_command --------------------------------------------------

def test_encode_rpc_command_simple():
    out = encode_rpc_command(0x01, b"AB")
    # [command=0x01][len=0x02][data=A,B][checksum]
    assert out[0] == 0x01
    assert out[1] == 0x02
    assert out[2:4] == b"AB"
    assert out[4] == (0x01 + 0x02 + ord("A") + ord("B")) & 0xFF


def test_encode_rpc_command_rejects_long_data():
    with pytest.raises(ValueError, match="too long"):
        encode_rpc_command(0x01, b"\x00" * 256)


def test_encode_rpc_command_rejects_bad_command_byte():
    with pytest.raises(ValueError, match="out of range"):
        encode_rpc_command(0x100, b"")


# --- encode_send_wifi_settings ------------------------------------------

def test_encode_send_wifi_settings_shape():
    out = encode_send_wifi_settings("MySSID", "secret")
    assert out[0] == ImprovRpcCommand.SEND_WIFI_SETTINGS
    # data = [6][MySSID][6][secret]
    data_len = out[1]
    data = out[2 : 2 + data_len]
    ssid_len = data[0]
    assert data[1 : 1 + ssid_len] == b"MySSID"
    pwd_len = data[1 + ssid_len]
    assert data[2 + ssid_len : 2 + ssid_len + pwd_len] == b"secret"
    # Checksum at the tail.
    assert out[-1] == sum(out[:-1]) & 0xFF


def test_encode_send_wifi_settings_rejects_oversize():
    with pytest.raises(ValueError):
        encode_send_wifi_settings("x" * 300, "y")
    with pytest.raises(ValueError):
        encode_send_wifi_settings("x", "y" * 300)


def test_encode_send_wifi_settings_handles_unicode():
    """Unicode SSIDs are uncommon but should survive the encode."""
    out = encode_send_wifi_settings("café", "p@ss")
    # 'café' utf-8 = 5 bytes
    assert out[2] == 5


# --- decode_rpc_result --------------------------------------------------

def _frame(command: int, entries: list[bytes]) -> bytes:
    data = b"".join(bytes([len(e)]) + e for e in entries)
    body = bytes([command, len(data)]) + data
    return body + bytes([sum(body) & 0xFF])


def test_decode_rpc_result_one_url():
    f = _frame(ImprovRpcCommand.SEND_WIFI_SETTINGS, [b"http://192.168.1.50:8643"])
    cmd, entries = decode_rpc_result(f)
    assert cmd == ImprovRpcCommand.SEND_WIFI_SETTINGS
    assert entries == [b"http://192.168.1.50:8643"]


def test_decode_rpc_result_multiple_entries():
    f = _frame(0x01, [b"http://a", b"http://b"])
    cmd, entries = decode_rpc_result(f)
    assert entries == [b"http://a", b"http://b"]


def test_decode_rpc_result_rejects_bad_checksum():
    f = bytearray(_frame(0x01, [b"x"]))
    f[-1] ^= 0xFF  # break the checksum
    with pytest.raises(ImprovError_, match="checksum"):
        decode_rpc_result(bytes(f))


def test_decode_rpc_result_rejects_length_mismatch():
    # Header says 5 data bytes, only 2 follow.
    with pytest.raises(ImprovError_, match="length mismatch"):
        decode_rpc_result(b"\x01\x05XY\x00")


def test_decode_rpc_result_rejects_short_frame():
    with pytest.raises(ImprovError_, match="too short"):
        decode_rpc_result(b"\x01")


# --- state / error byte decoding ----------------------------------------

@pytest.mark.parametrize("byte,state", [
    (0x01, ImprovState.AUTHORIZATION_REQUIRED),
    (0x02, ImprovState.AUTHORIZED),
    (0x03, ImprovState.PROVISIONING),
    (0x04, ImprovState.PROVISIONED),
])
def test_decode_state_known(byte, state):
    assert decode_state(byte) == state


def test_decode_state_unknown_raises():
    with pytest.raises(ImprovError_, match="unknown"):
        decode_state(0xAA)


@pytest.mark.parametrize("byte,err", [
    (0x00, ImprovError.NO_ERROR),
    (0x01, ImprovError.INVALID_RPC_PACKET),
    (0x02, ImprovError.UNKNOWN_RPC_COMMAND),
    (0x03, ImprovError.UNABLE_TO_PROVISION),
    (0x04, ImprovError.NOT_AUTHORIZED),
    (0xFF, ImprovError.UNKNOWN_ERROR),
])
def test_decode_error_known(byte, err):
    assert decode_error(byte) == err


def test_decode_error_unknown_byte_falls_back():
    assert decode_error(0xAA) == ImprovError.UNKNOWN_ERROR


# --- error-state → exception mapping ------------------------------------

def test_map_error_state_no_error_yields_none():
    assert map_error_state(ImprovError.NO_ERROR) is None


def test_map_error_state_wifi_failure_maps_to_WifiJoinFailed():
    assert map_error_state(ImprovError.UNABLE_TO_PROVISION) is WifiJoinFailed


def test_map_error_state_other_errors_map_to_generic():
    assert map_error_state(ImprovError.NOT_AUTHORIZED) is ImprovError_
    assert map_error_state(ImprovError.UNKNOWN_RPC_COMMAND) is ImprovError_


# --- exception code strings (for the JSON envelope) ---------------------

def test_exception_codes_are_stable():
    assert BleUnavailable("x").code == "ble_unavailable"
    assert WifiJoinFailed("x").code == "wifi_join_failed"
    assert ImprovError_("x").code == "ble_provisioning_failed"
