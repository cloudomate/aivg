"""Plaintext API-key authentication for the ESPHome transport.

Per-device API keys live in ``~/.aivg/devices/keys.json`` (mode 0600).
A connecting device presents its key in the ``password`` field of
``ConnectRequest`` (or the older ``AuthenticationRequest``). The
gateway compares the presented value against the keystore entry for
the device's ``client_info`` (the device-supplied identifier in
``HelloRequest.client_info``).

The optional ``bootstrap_key`` (set at gateway config time) lets an
**unregistered** device complete one Connect+Auth so the operator
can run ``aivg device adopt <device_id>`` — same flow WebRTC devices
already use.

Feature 017 OOS-001 defers the encrypted Noise-protocol mode to v1.1.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Optional


_DEFAULT_KEYSTORE = Path("~/.aivg/devices/keys.json").expanduser()
_KEYSTORE_SCHEMA = "aivg.devices.keys/v1"


class KeystoreResolver:
    """Reads per-device API keys from a JSON file (mode 0600).

    The file is created lazily on first :meth:`add_device`. Reads
    are best-effort: a missing file or unreadable entry returns
    ``None`` (caller treats as "device not registered").
    """

    def __init__(self, path: Path = _DEFAULT_KEYSTORE) -> None:
        self._path = path

    async def resolve(self, device_id: str) -> Optional[str]:
        """Return the API key for ``device_id``, or ``None`` if the
        device is not registered or the keystore is unreadable."""
        try:
            with open(self._path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        entry = (data.get("devices") or {}).get(device_id)
        if not isinstance(entry, dict):
            return None
        key = entry.get("api_key")
        return key if isinstance(key, str) and key else None

    def add_device(self, device_id: str, api_key: Optional[str] = None) -> str:
        """Insert (or rotate) the per-device key. Returns the key
        that was stored — generated cryptographically if not
        supplied. Creates the keystore file with mode 0600 if it
        does not exist yet."""
        if api_key is None:
            api_key = secrets.token_urlsafe(24)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {"_schema": _KEYSTORE_SCHEMA, "devices": {}}
        data.setdefault("devices", {})[device_id] = {"api_key": api_key}
        # Atomic write + mode 0600.
        tmp = self._path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self._path)
        return api_key

    def remove_device(self, device_id: str) -> bool:
        """Remove a device's key entry. Returns True if removed,
        False if the device was not registered."""
        try:
            with open(self._path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return False
        devices = data.get("devices") or {}
        if device_id not in devices:
            return False
        del devices[device_id]
        tmp = self._path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self._path)
        return True


def verify(
    presented: str,
    expected: Optional[str],
    *,
    bootstrap_key: Optional[str] = None,
) -> bool:
    """Constant-time compare ``presented`` against ``expected`` (the
    device's stored key) or against ``bootstrap_key`` (if non-empty,
    accepts unregistered devices through one Connect+Auth cycle).

    Empty / missing ``expected`` AND no bootstrap key configured ⇒
    auth fails. Used by ``EsphomeConnection._authenticate``.
    """
    if expected and hmac.compare_digest(presented, expected):
        return True
    if bootstrap_key and hmac.compare_digest(presented, bootstrap_key):
        return True
    return False
