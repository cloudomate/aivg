"""Feature 017 — US1 binding integration test.

Drives one full voice turn through the new ESPHome transport
end-to-end against the echo platform fixture. **No Hermes plugin
import** in this test — the test asserts that constraint explicitly
via an AST walk.

Per [contracts/esphome-transport.md § 8](../../specs/017-esphome-voice-transport/contracts/esphome-transport.md#8-contract-tests-binding)
row 7.
"""

from __future__ import annotations

import ast
import asyncio
import importlib
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
from aivg_core.transports.esphome.voice_protocol import Event  # noqa: E402

from fixtures.esphome_client import FakeEsphomeClient  # noqa: E402

_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "platforms"


@pytest.fixture
def echo_platform(monkeypatch):
    """Load the echo fixture under ``aivg_core.platforms.echo`` (same
    trick feature 015's tests use)."""
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
    """Grab an ephemeral TCP port the OS isn't using right now."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.asyncio
async def test_one_turn_against_echo_platform(echo_platform, tmp_path):
    """Drive one voice turn end-to-end against the echo platform via
    the new ESPHome transport. Reply audio MUST be non-empty and the
    pipeline lifecycle events MUST fire."""
    plat, mod = echo_platform
    mod.PLATFORM.reply_deltas = ["echo says hi"]
    # Counter-driven endpoint: 5 frames after the resampler emits them
    # → end_of_utterance. We push enough audio below to reach this.
    mod.PLATFORM.eou_after_frames = 5
    mod.PLATFORM._frame_count = 0

    # Set up a keystore in a tmp dir with one device's key.
    keystore = KeystoreResolver(tmp_path / "keys.json")
    keystore.add_device("test-device", "secret-test-key")

    # Build the transport.
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
        # Connect + auth.
        client = FakeEsphomeClient("test-device", "secret-test-key")
        await client.connect_and_auth("127.0.0.1", port)

        # Wait briefly for the gateway to register the device.
        await asyncio.sleep(0.1)
        assert "test-device" in {c.device_id for c in registry.list_clients()}

        # Start a voice pipeline + stream one short utterance.
        await client.start_voice_pipeline()
        # Push ~200 ms of audio in 20 ms wire frames (640 bytes each).
        pcm_chunk = b"\x12\x34" * 320  # 320 samples = 640 bytes @ 16 kHz
        for _ in range(10):
            await client.send_audio_pcm16k(pcm_chunk)
        # Signal end-of-audio.
        await client.send_audio_pcm16k(b"", end=True)

        # Wait for the pipeline to complete (RUN_END).
        got_run_end = await client.wait_for_event(Event.RUN_END, timeout=5.0)
        assert got_run_end, f"RUN_END not received; events seen: {client.events}"

        # The reply audio must be non-empty (echo synthesized
        # "echo:synth('echo says hi')" bytes; the adapter downsampled
        # them to 16 kHz; we captured the wire bytes).
        assert len(client.captured_audio) > 0, "no reply audio received"

        await client.disconnect()
    finally:
        await transport.stop()


def test_no_hermes_imports_in_this_test():
    """Constitutional binding: the integration test that proves the
    ESPHome transport works against a non-Hermes platform MUST NOT
    import the Hermes plugin. Verified by AST-walking this very file
    and asserting no ``aivg_core.platforms.hermes`` reference appears
    above the (intentionally-empty) test function body."""
    this_file = Path(__file__)
    tree = ast.parse(this_file.read_text())
    references: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "platforms.hermes" in node.module:
                references.append(f"from {node.module}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if "platforms.hermes" in alias.name:
                    references.append(f"import {alias.name}")
        elif isinstance(node, ast.Attribute):
            # Catch ``aivg_core.platforms.hermes.X`` style references.
            try:
                attr_chain = []
                cur = node
                while isinstance(cur, ast.Attribute):
                    attr_chain.append(cur.attr)
                    cur = cur.value
                if isinstance(cur, ast.Name):
                    attr_chain.append(cur.id)
                attr_chain.reverse()
                joined = ".".join(attr_chain)
                if "platforms.hermes" in joined:
                    references.append(joined)
            except Exception:  # noqa: BLE001
                pass

    assert references == [], (
        "Hermes plugin referenced in a platform-agnostic integration test: "
        + ", ".join(references)
    )
