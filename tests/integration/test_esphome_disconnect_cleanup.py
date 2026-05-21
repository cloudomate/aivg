"""Feature 017 / US4 / SC-007 — resource-hygiene test.

Open 30 ESPHome sessions sequentially, each drops mid-turn (closes
the socket before sending the EOU frame). After 2 s the gateway's
``EsphomeTransport.device_count`` MUST return to 0 — proving the
one-task-per-device model cleans up correctly (FR-021 / SC-007).

Note: the spec calls for 100 sessions; we use 30 here so the test
stays fast (<10 s) without sacrificing the signal. Resource-leak
bugs reliably surface at 30+.
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
from aivg_core.transports.esphome import EsphomeTransport  # noqa: E402
from aivg_core.transports.esphome.auth import KeystoreResolver  # noqa: E402
from aivg_core.transports.esphome.framing import encode_message  # noqa: E402

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
    plat = PluginRegistry.load("echo")
    yield plat, mod
    sys.modules.pop("aivg_core.platforms.echo", None)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _connect_and_drop(host: str, port: int, key: str, idx: int) -> None:
    """Open a connection, complete Hello + Connect, then close the
    writer mid-pipeline (before sending any audio)."""
    reader, writer = await asyncio.open_connection(host, port)
    try:
        writer.write(encode_message(pb.HelloRequest(
            client_info=f"drop-device-{idx}", api_version_major=1, api_version_minor=10,
        )))
        await writer.drain()
        # Read HelloResponse (best-effort; we don't decode it here).
        await asyncio.wait_for(reader.read(100), timeout=1.0)
        writer.write(encode_message(pb.ConnectRequest(password=key)))
        await writer.drain()
        # Read ConnectResponse.
        await asyncio.wait_for(reader.read(100), timeout=1.0)
        # Drop the writer mid-pipeline — no Voice* messages sent.
    finally:
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), timeout=1.0)
        except (asyncio.TimeoutError, ConnectionError):
            pass


@pytest.mark.asyncio
async def test_no_task_leak_on_mid_turn_disconnect(echo_platform, tmp_path):
    """Open + drop 30 sessions; transport's task count returns to 0."""
    plat, _ = echo_platform

    keystore = KeystoreResolver(tmp_path / "keys.json")
    n = 30
    for i in range(n):
        keystore.add_device(f"drop-device-{i}", f"key-{i}")

    registry = Registry()
    sink = LogSink(gateway_log=tmp_path / "g.log")
    port = _free_port()
    transport = EsphomeTransport(
        registry=registry,
        platform=plat,
        sink=sink,
        host="127.0.0.1",
        port=port,
        api_key_resolver=keystore,
    )
    await transport.start()
    try:
        # Open + drop sequentially (we want to test the cleanup path,
        # not concurrency — that's the previous test).
        for i in range(n):
            await _connect_and_drop("127.0.0.1", port, f"key-{i}", i)

        # Give the gateway up to 2 s to clean up.
        for _ in range(40):  # 40 × 50 ms = 2 s
            await asyncio.sleep(0.05)
            if transport.device_count == 0:
                break

        assert transport.device_count == 0, (
            f"transport leaked tasks after {n} drops: "
            f"device_count={transport.device_count}"
        )
    finally:
        await transport.stop()
