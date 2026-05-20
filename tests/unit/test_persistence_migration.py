"""Feature 012 T026 — atomic one-shot data-dir migration ~/.satellite → ~/.aivg.

See ``aivg_core.persistence.migrate_legacy_data_dir`` (R-3).

Covers:
* legacy state.json → new state.json byte-equivalent; old becomes
  ``.pre-aivg-rebrand.bak`` (never deleted).
* no legacy file → no-op.
* newer dst → no-op (idempotent).
* the per-device firmware/<type>/manifest.json subtree migrates with the
  same atomic-rename pattern.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from aivg_core import persistence


@pytest.fixture(autouse=True)
def _reset_sentinel():
    """The migration uses a module-level sentinel — clear it per test
    so the function actually runs."""
    persistence.reset_migration_sentinel_for_tests()
    yield
    persistence.reset_migration_sentinel_for_tests()


def test_state_file_migrates_with_bak_left_behind(tmp_path: Path):
    src = tmp_path / "satellite"
    dst = tmp_path / "aivg"
    src.mkdir()
    payload = {"schema_version": 1, "saved_at": 1.0, "clients": [], "device_limit": 10}
    (src / "state.json").write_text(json.dumps(payload))

    did = persistence.migrate_legacy_data_dir(
        src=src / "state.json", dst=dst / "state.json"
    )
    assert did is True
    assert (dst / "state.json").exists()
    assert json.loads((dst / "state.json").read_text()) == payload

    # Legacy file preserved with .bak suffix; never deleted (SC-005).
    assert (src / "state.json.pre-aivg-rebrand.bak").exists()
    assert not (src / "state.json").exists()


def test_no_legacy_file_is_noop(tmp_path: Path):
    src = tmp_path / "satellite"
    dst = tmp_path / "aivg"
    # `src` does not exist at all → no-op, no exception.
    did = persistence.migrate_legacy_data_dir(
        src=src / "state.json", dst=dst / "state.json"
    )
    assert did is False
    assert not (dst / "state.json").exists()


def test_newer_dst_wins_legacy_left_alone(tmp_path: Path):
    src = tmp_path / "satellite"
    dst = tmp_path / "aivg"
    src.mkdir()
    dst.mkdir()
    (src / "state.json").write_text('{"clients": [], "schema_version": 1}')
    time.sleep(0.05)  # ensure dst mtime > src mtime
    (dst / "state.json").write_text('{"clients": [{"keep": true}], "schema_version": 1}')

    did = persistence.migrate_legacy_data_dir(
        src=src / "state.json", dst=dst / "state.json"
    )
    assert did is False
    # dst untouched.
    assert "keep" in (dst / "state.json").read_text()
    # src ALSO untouched (no .bak yet) — operator may still want it.
    assert (src / "state.json").exists()


def test_migration_is_process_idempotent(tmp_path: Path):
    src = tmp_path / "satellite"
    dst = tmp_path / "aivg"
    src.mkdir()
    (src / "state.json").write_text('{"clients": [], "schema_version": 1}')

    persistence.migrate_legacy_data_dir(
        src=src / "state.json", dst=dst / "state.json"
    )
    # Second call in the same process is a no-op via the sentinel.
    did2 = persistence.migrate_legacy_data_dir(
        src=src / "state.json", dst=dst / "state.json"
    )
    assert did2 is False


def test_firmware_manifests_migrate(tmp_path: Path):
    legacy_fw = tmp_path / "satellite" / "firmware"
    new_fw = tmp_path / "aivg" / "firmware"
    (legacy_fw / "rpi").mkdir(parents=True)
    (legacy_fw / "esp32").mkdir(parents=True)
    (legacy_fw / "rpi" / "manifest.json").write_text('{"version": "0.1.0"}')
    (legacy_fw / "esp32" / "manifest.json").write_text('{"version": "0.2.0"}')

    persistence.migrate_legacy_data_dir(
        src=tmp_path / "no_state.json",  # state migration is a no-op
        dst=tmp_path / "aivg_state.json",
        legacy_firmware=legacy_fw,
        new_firmware=new_fw,
    )
    assert (new_fw / "rpi" / "manifest.json").read_text() == '{"version": "0.1.0"}'
    assert (new_fw / "esp32" / "manifest.json").read_text() == '{"version": "0.2.0"}'
    assert (legacy_fw / "rpi" / "manifest.json.pre-aivg-rebrand.bak").exists()
    assert (legacy_fw / "esp32" / "manifest.json.pre-aivg-rebrand.bak").exists()
