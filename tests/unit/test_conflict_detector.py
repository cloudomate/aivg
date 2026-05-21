"""Feature 019 / FR-004 — conflict detector loud-failure tests.

The detector exists to turn today's silent-shadow trap into a loud
RuntimeError. These tests pin the binding behavior:

- Both plugins present → RuntimeError with cleanup verb in the message.
- Multiple legacy plugins → all named in the error.
- Same name but `source != "bundled"` → no raise (only bundled auto-loads).
- Hermes plugin manager unavailable → log + return (don't block).

Mocks the Hermes plugin manager API so the tests are deterministic and
do not depend on the host's actual Hermes install state.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest


def _legacy_row(path: str = "/fake/plugins/satellite_webrtc") -> dict:
    """Fake plugin manifest row resembling the pre-019 bundled satellite."""
    return {
        "name": "satellite-webrtc-platform",
        "key": "satellite-webrtc-platform",
        "kind": "platform",
        "version": "0.1.0",
        "source": "bundled",
        "enabled": True,
        "path": path,
    }


def _entrypoint_row() -> dict:
    """Fake plugin manifest row resembling the post-019 entry-point plugin."""
    return {
        "name": "aivg-satellite",
        "key": "aivg-satellite",
        "kind": "standalone",
        "source": "entrypoint",
        "enabled": True,
    }


def test_conflict_detector_raises_when_legacy_bundled_plugin_present():
    """The binding silent-shadow regression test.

    Plugin manager returns BOTH the entry-point and the legacy bundled
    plugin. The detector MUST raise RuntimeError with a message
    containing the legacy directory path and a cleanup verb (`mv`).
    """
    from aivg_core.platforms.hermes.plugin_entrypoint.adapter import (
        _check_no_legacy_bundled_plugin,
    )

    fake_manager = type(
        "FM", (), {"list_plugins": lambda self: [
            _legacy_row("/fake/plugins/satellite_webrtc"),
            _entrypoint_row(),
        ]},
    )()

    with patch(
        "hermes_cli.plugins.get_plugin_manager", return_value=fake_manager
    ), patch("hermes_cli.plugins.discover_plugins"):
        with pytest.raises(RuntimeError) as excinfo:
            _check_no_legacy_bundled_plugin()

    msg = str(excinfo.value)
    assert "/fake/plugins/satellite_webrtc" in msg
    assert "mv " in msg  # cleanup verb appears in the message
    assert "aivg-satellite" in msg.lower() or "entry-point" in msg.lower()


def test_conflict_detector_enumerates_multiple_legacy_plugins():
    """If somehow more than one legacy plugin is loaded, ALL of them MUST
    appear in the error message — operator should not have to play
    whack-a-mole on subsequent restarts."""
    from aivg_core.platforms.hermes.plugin_entrypoint.adapter import (
        _check_no_legacy_bundled_plugin,
    )

    fake_manager = type(
        "FM", (), {"list_plugins": lambda self: [
            _legacy_row("/fake/plugins/satellite_webrtc"),
            _legacy_row("/fake/other/satellite_webrtc"),
            _entrypoint_row(),
        ]},
    )()

    with patch(
        "hermes_cli.plugins.get_plugin_manager", return_value=fake_manager
    ), patch("hermes_cli.plugins.discover_plugins"):
        with pytest.raises(RuntimeError) as excinfo:
            _check_no_legacy_bundled_plugin()

    msg = str(excinfo.value)
    assert "/fake/plugins/satellite_webrtc" in msg
    assert "/fake/other/satellite_webrtc" in msg


def test_conflict_detector_ignores_same_name_non_bundled_source():
    """A plugin with name == 'satellite-webrtc-platform' but
    source != 'bundled' MUST NOT trigger a conflict. Only bundled
    plugins auto-load and bind ports; entry-point/user-installed ones
    follow the opt-in path and aren't a silent-shadow risk."""
    from aivg_core.platforms.hermes.plugin_entrypoint.adapter import (
        _check_no_legacy_bundled_plugin,
    )

    not_bundled = dict(_legacy_row())
    not_bundled["source"] = "entrypoint"  # not a coexistence risk

    fake_manager = type(
        "FM", (), {"list_plugins": lambda self: [not_bundled, _entrypoint_row()]},
    )()

    with patch(
        "hermes_cli.plugins.get_plugin_manager", return_value=fake_manager
    ), patch("hermes_cli.plugins.discover_plugins"):
        # MUST NOT raise.
        _check_no_legacy_bundled_plugin()


def test_conflict_detector_swallows_hermes_api_failure(caplog):
    """If the Hermes plugin manager API raises (e.g. Hermes-internal
    refactor in a future release), the detector MUST log a warning and
    return silently rather than block the registration. A broken
    detector should not be more disruptive than the trap it exists to
    prevent."""
    from aivg_core.platforms.hermes.plugin_entrypoint.adapter import (
        _check_no_legacy_bundled_plugin,
    )

    def _explode(*_a, **_kw):
        raise RuntimeError("simulated Hermes API failure")

    with patch("hermes_cli.plugins.get_plugin_manager", side_effect=_explode), \
         patch("hermes_cli.plugins.discover_plugins"):
        with caplog.at_level(logging.WARNING):
            # MUST NOT raise.
            _check_no_legacy_bundled_plugin()

    # A warning MUST have been emitted naming the API failure.
    warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warning_records, "expected at least one WARNING-level log record"
    assert any("simulated Hermes API failure" in r.getMessage() for r in warning_records)
