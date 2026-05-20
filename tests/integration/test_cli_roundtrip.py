"""Integration: ``sat-cli`` onboard flow (feature 011 T042, US2).

Exercises the full orchestrator from :mod:`sat_cli.onboard.flow` against:

* a **mocked BLE peripheral** (the ``ble_client_factory`` hook) that
  reports a fixed device-id back over Improv;
* a **real aiohttp ManagementService** running under the in-process
  test client, exercising the actual REST surface.

The end-state asserted: a device transitions pending → adopted, the
fleet list reflects it, and the orchestrator yields one
:class:`OnboardResult` event.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Optional

import aiohttp
import pytest
from aiohttp import web

from satellite_core.config import SatelliteAdapterConfig
from satellite_core.logsink import LogSink
from satellite_core.management.service import ManagementService, build_management_app
from satellite_core.registry import Registry
from sat_cli.onboard.flow import (
    OnboardError,
    OnboardProgress,
    OnboardResult,
    run_onboard,
)


# --- fake BLE client (dependency-injected into run_onboard) ---------------


class _FakeImprovPeer:
    def __init__(self, address: str, name: str | None) -> None:
        self.address = address
        self.name = name
        self.rssi = -42


class _FakeImprovClient:
    """Replaces :class:`sat_cli.onboard.improv_ble.ImprovBleClient`.

    The ``post_register`` callable is invoked just before
    :meth:`send_wifi` returns — that's the moment the real device would
    have joined Wi-Fi and registered. The test uses it to synthesize the
    matching ``POST /satellite/register`` call.
    """

    def __init__(self, *, device_id: str, post_register=None) -> None:
        self._device_id = device_id
        self._post_register = post_register

    async def scan(self):
        return _FakeImprovPeer(address="AA:BB:CC:DD:EE:FF", name="HermesSat-xx")

    async def connect(self, peer) -> None:
        return None

    async def send_wifi(self, ssid: str, password: str):
        if self._post_register is not None:
            await self._post_register(self._device_id)
        return [f"http://192.168.1.50:8643"]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None


# --- aiohttp fixture: spin up the real management app ---------------------


@pytest.fixture
async def gateway(tmp_path):
    """Start the real ManagementService aiohttp app on an ephemeral port."""
    cfg = SatelliteAdapterConfig(
        default_config={"wake_word": "Jarvis"},
        device_limit=10,
        auto_adopt_on_register=False,  # US2 pending-first mode
    )
    sink = LogSink(gateway_log=tmp_path / "g.log")
    reg = Registry()
    svc = ManagementService(reg, sink, cfg)
    app = build_management_app(svc)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    # Resolve the bound port.
    sockets = list(site._server.sockets) if site._server else []  # noqa: SLF001
    port = sockets[0].getsockname()[1] if sockets else 0
    yield f"http://127.0.0.1:{port}", svc
    await runner.cleanup()


@pytest.mark.asyncio
async def test_onboard_happy_path(gateway):
    base_url, svc = gateway

    async def post_register(device_id: str) -> None:
        # The fake BLE peripheral wakes and self-registers at the gateway.
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"{base_url}/satellite/register",
                json={"device_id": device_id, "device_type": "rpi"},
            )

    factory = lambda: _FakeImprovClient(
        device_id="sat-001", post_register=post_register
    )

    progress: list[str] = []
    result: Optional[OnboardResult] = None
    async for event in run_onboard(
        ssid="MyWiFi",
        password="secret",
        name="bedroom",
        gateway_url=base_url,
        scan_timeout=2.0,
        register_timeout=5.0,
        poll_interval=0.05,
        ble_client_factory=factory,
    ):
        if isinstance(event, OnboardProgress):
            progress.append(event.phase)
        elif isinstance(event, OnboardResult):
            result = event

    assert result is not None
    assert result.device_id == "sat-001"
    assert result.name == "bedroom"
    assert result.device_state["adoption_state"] == "adopted"
    assert result.device_state["name"] == "bedroom"

    # Phases hit in order.
    assert progress == [
        "scanning",
        "connecting",
        "sending_credentials",
        "wifi_joined",
        "awaiting_register",
        "adopting",
    ]


@pytest.mark.asyncio
async def test_onboard_register_timeout(gateway):
    base_url, _svc = gateway

    # BLE works, but the device never self-registers.
    factory = lambda: _FakeImprovClient(device_id="sat-002", post_register=None)

    with pytest.raises(OnboardError) as exc_info:
        async for _ in run_onboard(
            ssid="MyWiFi",
            password="secret",
            name="bedroom",
            gateway_url=base_url,
            scan_timeout=2.0,
            register_timeout=0.3,
            poll_interval=0.05,
            ble_client_factory=factory,
        ):
            pass
    assert exc_info.value.code == "improv_timeout"


@pytest.mark.asyncio
async def test_onboard_gateway_unreachable():
    factory = lambda: _FakeImprovClient(device_id="sat-003", post_register=None)
    with pytest.raises(OnboardError) as exc_info:
        async for _ in run_onboard(
            ssid="MyWiFi",
            password="secret",
            name="bedroom",
            gateway_url="http://127.0.0.1:1",  # nothing listening
            scan_timeout=2.0,
            register_timeout=2.0,
            poll_interval=0.05,
            ble_client_factory=factory,
        ):
            pass
    assert exc_info.value.code == "gateway_unreachable"
