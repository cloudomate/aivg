"""Feature 019 / FR-004 — conflict-detector silent-success test.

The common case: only the post-019 entry-point plugin is loaded; the
detector MUST return silently without raising and without emitting any
WARNING-level log records. A warning storm on every gateway start
would be its own problem.
"""

from __future__ import annotations

import logging
from unittest.mock import patch


def test_conflict_detector_silent_when_only_entrypoint_plugin_present(caplog):
    """The post-019 default state: only `aivg-satellite` (source=entrypoint)
    is loaded. The detector MUST return None silently — no exception,
    no WARNING/ERROR-level log records."""
    from aivg_core.platforms.hermes.plugin_entrypoint.adapter import (
        _check_no_legacy_bundled_plugin,
    )

    fake_manager = type(
        "FM", (), {"list_plugins": lambda self: [
            {
                "name": "aivg-satellite",
                "key": "aivg-satellite",
                "kind": "standalone",
                "source": "entrypoint",
                "enabled": True,
            },
        ]},
    )()

    with patch(
        "hermes_cli.plugins.get_plugin_manager", return_value=fake_manager
    ), patch("hermes_cli.plugins.discover_plugins"):
        with caplog.at_level(logging.WARNING):
            result = _check_no_legacy_bundled_plugin()

    assert result is None
    warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warning_records == [], (
        "Conflict detector emitted WARNING/ERROR records on the common case "
        f"(should be silent): {[r.getMessage() for r in warning_records]}"
    )
