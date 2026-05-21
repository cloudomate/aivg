"""Feature 017 / US4 / SC-006 — multi-device concurrency test.

Spawn 4 in-process ESPHome clients concurrently against a single
``EsphomeTransport``; each runs one voice turn against the echo
platform. Per-task wall-clock MUST stay within 1.5× the single-device
budget (the test budget is loose: we just assert that all four
complete within 5 s wall-clock).
"""

from __future__ import annotations

import asyncio
import importlib.util
import socket
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("aioesphomeapi")

from aivg_core.logsink import LogSink  # noqa: E402
from aivg_core.platforms.base import PluginRegistry  # noqa: E402
from aivg_core.registry import Registry  # noqa: E402
from aivg_core.transports.esphome import EsphomeTransport  # noqa: E402
from aivg_core.transports.esphome.auth import KeystoreResolver  # noqa: E402
from aivg_core.transports.esphome.voice_protocol import Event  # noqa: E402

from fixtures.esphome_client import FakeEsphomeClient  # noqa: E402

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


async def _drive_one_device(host: str, port: int, device_id: str, key: str) -> dict:
    """Connect one client, run one turn, return per-device metrics."""
    client = FakeEsphomeClient(device_id, key)
    t0 = time.monotonic()
    await client.connect_and_auth(host, port)
    await client.start_voice_pipeline()
    pcm_chunk = b"\x12\x34" * 320
    for _ in range(10):
        await client.send_audio_pcm16k(pcm_chunk)
    await client.send_audio_pcm16k(b"", end=True)
    got_run_end = await client.wait_for_event(Event.RUN_END, timeout=5.0)
    elapsed = time.monotonic() - t0
    audio_bytes = len(client.captured_audio)
    await client.disconnect()
    return {
        "device_id": device_id,
        "elapsed": elapsed,
        "got_run_end": got_run_end,
        "audio_bytes": audio_bytes,
    }


@pytest.mark.asyncio
async def test_four_concurrent_turns(echo_platform, tmp_path):
    """4 ESPHome clients concurrently each complete one turn. All
    four MUST succeed within a shared budget (SC-006)."""
    plat, mod = echo_platform
    mod.PLATFORM.reply_deltas = ["concurrent reply"]
    mod.PLATFORM.eou_after_frames = 5
    mod.PLATFORM._frame_count = 0

    n = 4
    keystore = KeystoreResolver(tmp_path / "keys.json")
    keys = {}
    for i in range(n):
        device_id = f"concurrent-device-{i}"
        keys[device_id] = keystore.add_device(device_id, f"key-{i}")

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
        single_device_baseline = 2.0  # generous; real budget is < 1 s
        t0 = time.monotonic()
        results = await asyncio.gather(
            *(
                _drive_one_device("127.0.0.1", port, dev, key)
                for dev, key in keys.items()
            )
        )
        wall = time.monotonic() - t0

        for r in results:
            assert r["got_run_end"], (
                f"device {r['device_id']} did not get RUN_END: {r}"
            )
            # Loose budget: SC-006 says 1.5× single-device; we use 5 s as
            # a hard ceiling that comfortably accommodates that.
            assert r["elapsed"] < 1.5 * single_device_baseline, (
                f"device {r['device_id']} took {r['elapsed']:.2f}s "
                f"(budget {1.5 * single_device_baseline:.2f}s)"
            )
        # All four ran concurrently — total wall < N × per-device time.
        assert wall < n * single_device_baseline / 2, (
            f"4 concurrent devices took {wall:.2f}s — not concurrent "
            f"(expected < {n * single_device_baseline / 2:.2f}s)"
        )
    finally:
        await transport.stop()
