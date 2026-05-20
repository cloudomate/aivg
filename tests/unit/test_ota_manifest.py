"""Unit: OtaManifest validation + loader (feature 011 T065, US4).

* sha256 MUST be 64 lowercase hex chars (constitution II / R-6).
* device_type == "browser" rejected at load (sanctioned divergence).
* Missing-file → FileNotFoundError.
"""

from __future__ import annotations

import json

import pytest

from aivg_core.logsink import LogSink
from aivg_core.management.ota import BrowserNotOtaEligible, OtaService
from aivg_core.models import OtaManifest


# --- model-level validation ---------------------------------------------


def test_sha256_must_be_64_lowercase_hex():
    with pytest.raises(ValueError, match="sha256"):
        OtaManifest(
            device_type="rpi",
            version="0.2.0",
            url="http://x/y",
            sha256="ABC",  # too short, mixed case
        )


def test_sha256_uppercase_rejected():
    with pytest.raises(ValueError, match="sha256"):
        OtaManifest(
            device_type="rpi",
            version="0.2.0",
            url="http://x/y",
            sha256="A" * 64,  # uppercase
        )


def test_browser_device_type_rejected_at_construction():
    with pytest.raises(ValueError, match="browser"):
        OtaManifest(
            device_type="browser",
            version="0.0",
            url="http://x/y",
            sha256="a" * 64,
        )


def test_valid_sha256_accepted():
    m = OtaManifest(
        device_type="rpi",
        version="0.2.0",
        url="http://x/y",
        sha256="a1b2c3d4" * 8,  # 64 lowercase hex
        signature=None,
        changelog="ok",
    )
    assert m.version == "0.2.0"


# --- service-level loader -----------------------------------------------


def test_load_manifest_browser_raises(tmp_path):
    svc = OtaService(LogSink(gateway_log=tmp_path / "g.log"), firmware_dir=tmp_path)
    with pytest.raises(BrowserNotOtaEligible):
        svc.load_manifest("browser")


def test_load_manifest_missing_raises_filenotfound(tmp_path):
    svc = OtaService(LogSink(gateway_log=tmp_path / "g.log"), firmware_dir=tmp_path)
    with pytest.raises(FileNotFoundError):
        svc.load_manifest("rpi")


def test_load_manifest_happy_path(tmp_path):
    (tmp_path / "rpi").mkdir()
    (tmp_path / "rpi" / "manifest.json").write_text(json.dumps({
        "device_type": "rpi",
        "version": "0.3.0",
        "url": "http://x",
        "sha256": "c" * 64,
        "signature": None,
        "changelog": "",
    }))
    svc = OtaService(LogSink(gateway_log=tmp_path / "g.log"), firmware_dir=tmp_path)
    m = svc.load_manifest("rpi")
    assert m.version == "0.3.0"
    assert m.sha256 == "c" * 64
