"""Persistence (feature 011 T018, R-5).

Atomic write + load round-trip; partial-write atomicity (tmp file is
removed by ``os.replace``, not visible mid-write); unknown schema_version
yields empty start (no destructive migration).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from satellite_core.models import (
    AdoptionState,
    ClientStatus,
    ConnectedClient,
    OtaState,
    SatelliteConfig,
)
from satellite_core import persistence


@pytest.fixture
def state_path(tmp_path: Path) -> Path:
    return tmp_path / "state.json"


def _make_client(device_id: str = "kitchen", name: str = "kitchen") -> ConnectedClient:
    return ConnectedClient(
        device_id=device_id,
        device_type="rpi",
        firmware_version="0.1.0",
        ip_address="192.168.1.50",
        status=ClientStatus.ONLINE,
        config=SatelliteConfig(wake_word="hey_jarvis", input_volume=0.8),
        name=name,
        adoption_state=AdoptionState.ADOPTED,
        config_version=3,
        ota_state=OtaState.IDLE,
    )


def test_round_trip(state_path: Path) -> None:
    c = _make_client()
    out = persistence.write_snapshot([c], device_limit=10, path=state_path)
    assert out == state_path
    assert state_path.exists()

    loaded = persistence.load_snapshot(state_path)
    assert len(loaded) == 1
    got = loaded[0]
    assert got.device_id == "kitchen"
    assert got.name == "kitchen"
    assert got.adoption_state is AdoptionState.ADOPTED
    assert got.config.wake_word == "hey_jarvis"
    assert got.config.input_volume == 0.8
    assert got.config_version == 3


def test_missing_file_returns_empty(tmp_path: Path) -> None:
    assert persistence.load_snapshot(tmp_path / "nope.json") == []


def test_unknown_schema_version_returns_empty(state_path: Path) -> None:
    state_path.write_text('{"schema_version": 99, "clients": []}')
    assert persistence.load_snapshot(state_path) == []


def test_malformed_row_is_skipped_not_fatal(state_path: Path) -> None:
    state_path.write_text(
        '{"schema_version": 1, "saved_at": 0, "device_limit": 10, '
        '"clients": [{"missing_device_id": true}, '
        '{"device_id":"ok","device_type":"esp32","status":"online",'
        '"adoption_state":"adopted","ota_state":"idle"}]}'
    )
    loaded = persistence.load_snapshot(state_path)
    assert len(loaded) == 1
    assert loaded[0].device_id == "ok"


def test_atomicity_tmp_file_is_cleaned(state_path: Path) -> None:
    persistence.write_snapshot([_make_client()], device_limit=10, path=state_path)
    tmp = state_path.with_suffix(state_path.suffix + ".tmp")
    # os.replace consumes the tmp file; it MUST NOT be left behind.
    assert not tmp.exists()


def test_corrupt_json_returns_empty(state_path: Path) -> None:
    state_path.write_text("{not json")
    assert persistence.load_snapshot(state_path) == []
