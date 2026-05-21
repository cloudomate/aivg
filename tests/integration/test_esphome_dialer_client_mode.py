"""Feature 017 — client-mode (dialer) integration test.

Proves the dialer can DIAL OUT to a real ESPHome-compatible server
(simulated here with a tiny in-process ESPHome SERVER fixture that
speaks the device side of the protocol) and complete the Hello +
Auth handshake. Critical for the "real ESPHome firmware device"
hardware use case (T046) — real devices ARE the server.
"""

from __future__ import annotations

import asyncio
import importlib.util
import socket
import sys
from pathlib import Path

import pytest

pytest.importorskip("aioesphomeapi")

import aioesphomeapi.api_pb2 as pb  # noqa: E402

from aivg_core.logsink import LogSink  # noqa: E402
from aivg_core.platforms.base import PluginRegistry  # noqa: E402
from aivg_core.registry import Registry  # noqa: E402
from aivg_core.transports.esphome.dialer import EsphomeDeviceDialer  # noqa: E402
from aivg_core.transports.esphome.framing import (  # noqa: E402
    encode_message,
    read_next_message,
)

_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "platforms"


@pytest.fixture
def echo_platform(monkeypatch):
    monkeypatch.syspath_prepend(str(_FIXTURE_DIR.parent))
    spec = importlib.util.spec_from_file_location(
        "aivg_core.platforms.echo", _FIXTURE_DIR / "echo" / "__init__.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setitem(sys.modules, "aivg_core.platforms.echo", mod)
    yield PluginRegistry.load("echo"), mod
    sys.modules.pop("aivg_core.platforms.echo", None)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeEsphomeDeviceServer:
    """In-process ESPHome-API SERVER fixture (simulating a real
    ESP32 device). The dialer connects TO this; we respond to Hello
    + Connect with the standard happy-path. Exposes ``await
    ready_event`` so the test can sync after handshake."""

    def __init__(self, expected_api_key: str) -> None:
        self._expected = expected_api_key
        self._server: asyncio.base_events.Server | None = None
        self.handshake_count = 0
        self.last_password_seen: str | None = None
        self.ready_event = asyncio.Event()

    async def start(self, port: int) -> None:
        self._server = await asyncio.start_server(
            self._handle, host="127.0.0.1", port=port
        )

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        try:
            await self._server.wait_closed()
        except Exception:  # noqa: BLE001
            pass

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            # Step 1: receive HelloRequest from AIVG.
            opcode, msg = await read_next_message(reader)
            assert isinstance(msg, pb.HelloRequest), f"got {type(msg).__name__}"
            # Reply with HelloResponse advertising "device" identity.
            writer.write(encode_message(pb.HelloResponse(
                api_version_major=1,
                api_version_minor=10,
                server_info="fake-esp32-device",
                name="fake-esp32-device",
            )))
            await writer.drain()
            # Step 2: receive ConnectRequest with the api_key.
            opcode, msg = await read_next_message(reader)
            assert isinstance(msg, pb.ConnectRequest), f"got {type(msg).__name__}"
            self.last_password_seen = msg.password
            ok = msg.password == self._expected
            writer.write(encode_message(pb.ConnectResponse(
                invalid_password=(not ok),
            )))
            await writer.drain()
            if not ok:
                return  # device closes
            # Step 3: receive SubscribeVoiceAssistantRequest (the dialer
            # sends this immediately after Connect succeeds).
            opcode, msg = await read_next_message(reader)
            assert isinstance(msg, pb.SubscribeVoiceAssistantRequest), (
                f"expected SubscribeVoiceAssistantRequest, got {type(msg).__name__}"
            )
            self.handshake_count += 1
            self.ready_event.set()
            # Stay open for the test's lifetime — keep recv'ing
            # (and ignoring) any further messages.
            while True:
                opcode, _ = await read_next_message(reader)
        except (
            ConnectionError,
            asyncio.IncompleteReadError,
            asyncio.CancelledError,
        ):
            return
        except AssertionError:
            raise
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass


@pytest.mark.asyncio
async def test_dialer_completes_handshake_against_fake_device(
    echo_platform, tmp_path
):
    """AIVG's dialer dials a fake ESPHome-API server (simulating a
    real device) and completes Hello + Connect + Subscribe. The
    device must then appear in the registry tagged
    ``transport='esphome_api'``."""
    plat, _ = echo_platform

    api_key = "fake-device-api-key"
    device_port = _free_port()

    fake_device = FakeEsphomeDeviceServer(expected_api_key=api_key)
    await fake_device.start(device_port)
    try:
        registry = Registry()
        sink = LogSink(gateway_log=tmp_path / "g.log")
        dialer = EsphomeDeviceDialer(
            registry=registry,
            platform=plat,
            sink=sink,
            devices=[{
                "host": "127.0.0.1",
                "port": device_port,
                "device_id": "fake-esp32-device",
                "api_key": api_key,
            }],
        )
        await dialer.start()
        try:
            # Wait for the fake device to see the handshake.
            await asyncio.wait_for(fake_device.ready_event.wait(), timeout=5.0)
            assert fake_device.handshake_count == 1
            assert fake_device.last_password_seen == api_key
            # AIVG's registry must show the device as adopted.
            adopted = {c.device_id: c for c in registry.list_clients()}
            assert "fake-esp32-device" in adopted
            assert adopted["fake-esp32-device"].transport == "esphome_api"
        finally:
            await dialer.stop()
    finally:
        await fake_device.stop()


@pytest.mark.asyncio
async def test_dialer_rejects_wrong_api_key(echo_platform, tmp_path):
    """If AIVG's configured api_key doesn't match the device's, the
    device returns ConnectResponse(invalid_password=True) and the
    dialer logs the failure. The device must NOT appear adopted."""
    plat, _ = echo_platform

    device_port = _free_port()
    fake_device = FakeEsphomeDeviceServer(expected_api_key="correct-key")
    await fake_device.start(device_port)
    try:
        registry = Registry()
        sink = LogSink(gateway_log=tmp_path / "g.log")
        dialer = EsphomeDeviceDialer(
            registry=registry,
            platform=plat,
            sink=sink,
            devices=[{
                "host": "127.0.0.1",
                "port": device_port,
                "device_id": "fake-esp32-device",
                "api_key": "WRONG-key",
            }],
        )
        await dialer.start()
        try:
            # Give the dialer a moment to attempt the handshake.
            await asyncio.sleep(0.3)
            # The dialer should NOT have registered the device (auth failed).
            adopted = {c.device_id for c in registry.list_clients()}
            assert "fake-esp32-device" not in adopted
            assert fake_device.last_password_seen == "WRONG-key"
        finally:
            await dialer.stop()
    finally:
        await fake_device.stop()
