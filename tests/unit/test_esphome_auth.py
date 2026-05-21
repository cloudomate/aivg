"""Feature 017 — keystore + auth unit tests for the ESPHome transport.

Per [contracts/esphome-transport.md § 8](../../specs/017-esphome-voice-transport/contracts/esphome-transport.md#8-contract-tests-binding)
rows 3-4.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from aivg_core.transports.esphome.auth import KeystoreResolver, verify


@pytest.fixture
def keystore_path(tmp_path: Path) -> Path:
    return tmp_path / "keys.json"


@pytest.mark.asyncio
async def test_resolve_missing_file_returns_none(keystore_path):
    ks = KeystoreResolver(keystore_path)
    assert await ks.resolve("device-1") is None


@pytest.mark.asyncio
async def test_add_and_resolve_device(keystore_path):
    ks = KeystoreResolver(keystore_path)
    key = ks.add_device("device-1", "secret-abc")
    assert key == "secret-abc"
    assert await ks.resolve("device-1") == "secret-abc"
    # Mode 0600 on the file
    assert (os.stat(keystore_path).st_mode & 0o777) == 0o600


@pytest.mark.asyncio
async def test_add_generates_key_when_none_provided(keystore_path):
    ks = KeystoreResolver(keystore_path)
    key = ks.add_device("device-1")
    assert isinstance(key, str) and len(key) >= 16  # cryptographic length
    assert await ks.resolve("device-1") == key


@pytest.mark.asyncio
async def test_rotate_overwrites_existing(keystore_path):
    ks = KeystoreResolver(keystore_path)
    ks.add_device("device-1", "old")
    ks.add_device("device-1", "new")
    assert await ks.resolve("device-1") == "new"


@pytest.mark.asyncio
async def test_remove_device(keystore_path):
    ks = KeystoreResolver(keystore_path)
    ks.add_device("device-1", "k1")
    ks.add_device("device-2", "k2")
    assert ks.remove_device("device-1") is True
    assert await ks.resolve("device-1") is None
    assert await ks.resolve("device-2") == "k2"
    # Removing again returns False (idempotent-friendly)
    assert ks.remove_device("device-1") is False


def test_verify_valid_api_key():
    """The exact device-specific key passes."""
    assert verify("secret", "secret") is True


def test_verify_invalid_key_fails():
    assert verify("wrong", "secret") is False
    assert verify("", "secret") is False


def test_verify_missing_expected_fails():
    """No registered key + no bootstrap key → fail."""
    assert verify("anything", None) is False
    assert verify("anything", "") is False


def test_verify_bootstrap_key_accepts_unregistered():
    """An unregistered device can authenticate against the bootstrap key."""
    assert verify("bootstrap-secret", None, bootstrap_key="bootstrap-secret") is True
    assert verify("wrong-bootstrap", None, bootstrap_key="bootstrap-secret") is False


def test_verify_constant_time():
    """The hmac.compare_digest path is the implementation; sanity-check
    that obviously-wrong keys still return False."""
    assert verify("a" * 100, "b" * 100) is False
