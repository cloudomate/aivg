"""US1 (P1) integration: speech → STT → agent → TTS → speech, ≤1.5 s (SC-001)."""

import asyncio
import time

import pytest

from aivg_core.logsink import LogSink
from aivg_core.models import VoiceSession
from aivg_core.webrtc.session import Session

pytestmark = pytest.mark.asyncio


async def test_p1_loop_and_latency(tmp_path, bridge, transport):
    sink = LogSink(gateway_log=tmp_path / "g.log")
    model = VoiceSession(session_id="s1", device_id="browser-1")
    sess = Session(model, transport, bridge, sink)

    runner = asyncio.create_task(sess.run())
    t0 = time.monotonic()
    transport.push_utterance("hello hermes")

    # wait for the spoken reply
    for _ in range(200):
        if transport.sent:
            break
        await asyncio.sleep(0.005)
    elapsed = time.monotonic() - t0

    assert transport.sent == [b"AUDIO:echo: hello hermes"]
    assert elapsed < 1.5  # SC-001
    assert bridge.calls == ["stt", "agent", "tts"]

    transport.end_stream()
    await asyncio.wait_for(runner, timeout=2)
    assert transport.closed


async def test_empty_agent_reply_returns_to_listening(tmp_path):
    from fakes import FakeHermesBridge, FakeTransport

    sink = LogSink(gateway_log=tmp_path / "g.log")
    tr = FakeTransport()
    sess = Session(
        VoiceSession(session_id="s2", device_id="d"),
        tr,
        FakeHermesBridge(empty_reply=True),
        sink,
    )
    runner = asyncio.create_task(sess.run())
    tr.push_utterance("anything")
    await asyncio.sleep(0.05)
    assert tr.sent == []  # no broken audio emitted
    tr.end_stream()
    await asyncio.wait_for(runner, timeout=2)


async def test_all_providers_unavailable_is_perceptible(tmp_path):
    from fakes import FakeHermesBridge, FakeTransport

    sink = LogSink(gateway_log=tmp_path / "g.log")
    tr = FakeTransport()
    sess = Session(
        VoiceSession(session_id="s3", device_id="d"),
        tr,
        FakeHermesBridge(providers_down=True),
        sink,
    )
    runner = asyncio.create_task(sess.run())
    tr.push_utterance("hi")
    for _ in range(200):
        if tr.sent:
            break
        await asyncio.sleep(0.005)
    assert tr.sent == [b"__PROVIDERS_UNAVAILABLE__"]  # FR-015: not silence
    tr.end_stream()
    await asyncio.wait_for(runner, timeout=2)
