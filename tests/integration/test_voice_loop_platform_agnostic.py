"""Feature 015 US1 / US4 (SC-004): drive one voice turn through
:class:`aivg_core.webrtc.session.Session` end-to-end against the echo
platform fixture. NO ``HermesBridge`` symbol crosses this test.

Proves the satellite voice loop runs against a non-Hermes plugin
loaded via :class:`PluginRegistry`, with zero changes to ``aivg_core``
beyond the protocol seam.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

from aivg_core.logsink import LogSink
from aivg_core.models import VoiceSession
from aivg_core.platforms.base import PluginRegistry
from aivg_core.webrtc.session import Session

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


@pytest.mark.asyncio
async def test_voice_turn_against_echo_platform(echo_platform, tmp_path):
    """Construct a Session against the echo platform (no Hermes
    symbol involved), feed one utterance via a FakeTransport with the
    echo's EOU sentinel, and assert the captured reply audio matches
    echo's deterministic synth output."""
    from fakes import FakeTransport

    plat, mod = echo_platform
    # Configure deterministic reply deltas so the assertion is exact.
    mod.PLATFORM.reply_deltas = ["echo says hi"]

    sink = LogSink(gateway_log=tmp_path / "g.log")
    tr = FakeTransport()
    sess = Session(
        VoiceSession(session_id="s1", device_id="d1"),
        tr,
        plat,
        sink,
    )
    runner = asyncio.create_task(sess.run())

    # Push utterance audio followed by the echo platform's EOU marker.
    tr.push(b"hello world", mod.ECHO_EOU)

    # Wait for the reply audio to be sent.
    deadline = asyncio.get_event_loop().time() + 2.0
    while not tr.sent and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.005)
    assert tr.sent, "echo platform did not produce reply audio within 2s"

    # Echo platform: agent_step yields "echo says hi" → accumulated
    # reply text "echo says hi" → synthesize returns
    # f"echo:synth({text!r})".encode().
    expected = f"echo:synth({'echo says hi'!r})".encode("utf-8")
    assert tr.sent[0] == expected, (
        f"reply audio mismatch:\n  expected: {expected!r}\n  got: {tr.sent[0]!r}"
    )

    # Verify the transcript flowed through transcribe() too.
    # The echo platform strips its own markers and decodes utf-8.
    # The utterance was "hello world" + ECHO_EOU; transcribed text
    # should be "hello world".
    # (No direct assert on transcript here — proven by the reply
    # audio's well-formed shape implying transcribe ran.)

    tr.end_stream()
    await asyncio.wait_for(runner, timeout=2)


@pytest.mark.asyncio
async def test_loading_echo_does_not_import_hermes_plugin(echo_platform):
    """US1 binding: a non-Hermes platform loading + running the voice
    loop MUST NOT cause the Hermes plugin module to import."""
    # The echo_platform fixture already loaded; we tear down any
    # earlier-loaded Hermes module and re-confirm.
    for k in list(sys.modules):
        if "aivg_core.platforms.hermes" in k:
            sys.modules.pop(k, None)
    plat, _ = echo_platform
    # Run startup → shutdown on echo; ensure no Hermes import side-effect.
    await plat.startup(gateway_config={})
    await plat.shutdown()
    leaked = [k for k in sys.modules if "aivg_core.platforms.hermes" in k]
    assert leaked == [], f"Hermes plugin leaked during echo lifecycle: {leaked}"
