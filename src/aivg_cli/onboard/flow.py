"""Onboarding orchestrator (feature 011 T050, US2).

Glues the local Improv-over-BLE step to the gateway's REST surface:

1. Scan BLE for an Improv peripheral.
2. Send Wi-Fi credentials over BLE.
3. Wait for the device to come up on Wi-Fi and POST ``/satellite/register``.
4. Adopt the now-registered device with ``POST /satellite/{id}/adopt``.

Each phase emits a typed progress event the CLI surfaces as NDJSON under
``--json``. Failures are mapped to stable ``error.code`` values
documented in :mod:`aivg_cli.exit_codes`.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import AsyncIterator, Optional

from ..rest_client import ManagementClient, RestError
from .improv_ble import (
    BleUnavailable,
    ImprovBleClient,
    ImprovError_,
    ImprovTimeout,
    WifiJoinFailed,
)


@dataclass
class OnboardProgress:
    phase: str
    detail: Optional[dict] = None


@dataclass
class OnboardResult:
    device_id: str
    name: str
    device_state: dict


class OnboardError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


async def run_onboard(
    *,
    ssid: str,
    password: str,
    name: str,
    gateway_url: str,
    scan_timeout: float = 30.0,
    register_timeout: float = 90.0,
    poll_interval: float = 1.0,
    ble_client_factory=None,
) -> AsyncIterator:
    """Run the full onboarding flow as an async iterator that yields
    :class:`OnboardProgress` events and finally one :class:`OnboardResult`.

    ``ble_client_factory`` is dependency-injectable for tests (it must
    return an :class:`ImprovBleClient`-compatible context manager).
    """
    if not ssid or not name:
        raise OnboardError("bad_input", "ssid and name are required")

    factory = ble_client_factory or (lambda: ImprovBleClient(scan_timeout=scan_timeout))

    # Snapshot the pending set BEFORE BLE so the device's self-register
    # during/after Improv shows up as a "new" entry. Doing this at the
    # very start of the flow (rather than after BLE) covers fast BLE
    # peripherals that register before send_wifi returns.
    pending_before: set[str] = set()
    async with ManagementClient(gateway_url) as _pre:
        try:
            pending_before = {
                r["device_id"] for r in await _pre.list_devices(state="pending")
            }
        except RestError as e:
            raise OnboardError(e.code, e.message) from e

    # --- 1. BLE scan + provisioning -------------------------------------
    yield OnboardProgress("scanning")
    try:
        async with factory() as ble:
            try:
                peer = await ble.scan()
            except BleUnavailable as e:
                raise OnboardError("ble_unavailable", str(e)) from e
            except ImprovTimeout as e:
                raise OnboardError("improv_timeout", str(e)) from e

            yield OnboardProgress(
                "connecting",
                {"address": peer.address, "name": peer.name},
            )
            try:
                await ble.connect(peer)
            except BleUnavailable as e:
                raise OnboardError("ble_unavailable", str(e)) from e
            except ImprovError_ as e:
                raise OnboardError("ble_provisioning_failed", str(e)) from e

            yield OnboardProgress("sending_credentials")
            try:
                urls = await ble.send_wifi(ssid=ssid, password=password)
            except WifiJoinFailed as e:
                raise OnboardError("wifi_join_failed", str(e)) from e
            except ImprovTimeout as e:
                raise OnboardError("improv_timeout", str(e)) from e
            except ImprovError_ as e:
                raise OnboardError("ble_provisioning_failed", str(e)) from e

            yield OnboardProgress("wifi_joined", {"device_urls": urls})
    except OnboardError:
        raise
    except Exception as e:  # noqa: BLE001 - guard against bleak surprises
        raise OnboardError("ble_provisioning_failed", str(e)) from e

    # --- 2. Wait for the device to self-register at the gateway ---------
    yield OnboardProgress("awaiting_register", {"timeout_s": register_timeout})
    async with ManagementClient(gateway_url) as client:
        device_id = await _wait_for_pending_device(
            client,
            name_hint=name,
            timeout=register_timeout,
            poll_interval=poll_interval,
            before=pending_before,
        )

        # --- 3. Adopt --------------------------------------------------
        yield OnboardProgress("adopting", {"device_id": device_id, "name": name})
        try:
            state = await client._request(
                "POST",
                f"/satellite/{device_id}/adopt",
                json={"name": name},
            )
        except RestError as e:
            raise OnboardError(e.code, e.message) from e

    yield OnboardResult(device_id=device_id, name=name, device_state=state)


async def _wait_for_pending_device(
    client: ManagementClient,
    *,
    name_hint: str,
    timeout: float,
    poll_interval: float,
    before: set[str],
) -> str:
    """Poll ``GET /satellite/list?state=pending`` until a device id that
    was NOT in ``before`` appears."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            rows = await client.list_devices(state="pending")
        except RestError as e:
            raise OnboardError(e.code, e.message) from e
        for r in rows:
            if r["device_id"] not in before:
                return r["device_id"]
        await asyncio.sleep(poll_interval)
    raise OnboardError(
        "improv_timeout",
        f"device {name_hint!r} did not register within {timeout:.0f}s",
    )
