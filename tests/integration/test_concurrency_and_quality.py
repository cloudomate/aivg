"""Polish: SC-005 concurrency, SC-002 no dropped turns, SC-004 parity,
SC-006 control plane available with no active call.

(Closes analyze gaps E1/E2/E3.)
"""

import asyncio
import time

import pytest

from satellite_core.config import SatelliteAdapterConfig
from satellite_core.logsink import LogSink
from satellite_core.management import ManagementService
from satellite_core.models import VoiceSession
from satellite_core.registry import Registry
from satellite_core.webrtc.session import Session

pytestmark = pytest.mark.asyncio


async def _one_conversation(idx, tmp_path):
    from fakes import FakeHermesBridge, FakeTransport

    sink = LogSink(gateway_log=tmp_path / f"g{idx}.log")
    tr = FakeTransport()
    sess = Session(
        VoiceSession(session_id=f"s{idx}", device_id=f"d{idx}"),
        tr,
        FakeHermesBridge(agent_latency=0.02, tts_latency=0.02),
        sink,
    )
    runner = asyncio.create_task(sess.run())
    t0 = time.monotonic()
    tr.push_utterance(f"hello {idx}")
    while not tr.sent:
        await asyncio.sleep(0.005)
    latency = time.monotonic() - t0
    tr.end_stream()
    await asyncio.wait_for(runner, timeout=3)
    return latency, tr.sent[0]


async def test_sc005_ten_plus_concurrent_sessions(tmp_path):
    results = await asyncio.gather(*[_one_conversation(i, tmp_path) for i in range(12)])
    for idx, (latency, reply) in enumerate(results):
        assert reply == f"AUDIO:echo: hello {idx}".encode()
        assert latency < 1.5 * 1.5  # SC-005: within 1.5x the SC-001 budget


async def test_sc002_no_dropped_turns_over_a_multi_turn_session(tmp_path):
    from fakes import FakeHermesBridge, FakeTransport

    sink = LogSink(gateway_log=tmp_path / "g.log")
    tr = FakeTransport()
    sess = Session(
        VoiceSession(session_id="s", device_id="d"), tr, FakeHermesBridge(), sink
    )
    runner = asyncio.create_task(sess.run())
    n = 20
    for i in range(n):
        tr.push_utterance(f"q{i}")
        while len(tr.sent) <= i:
            await asyncio.sleep(0.002)
    assert len(tr.sent) == n  # 100% of turns produced a reply (≥95% SC-002)
    tr.end_stream()
    await asyncio.wait_for(runner, timeout=3)


async def test_sc004_adapter_path_matches_direct_bridge_output(tmp_path):
    """No measurable quality regression vs calling the bridge directly."""
    from fakes import FakeHermesBridge, FakeTransport
    from satellite_core.platforms.hermes.bridge import SessionCtx

    b = FakeHermesBridge()
    ctx = SessionCtx(device_id="d", session_id="s")
    direct_text = (await b.agent_turn("ping", ctx=ctx)).text
    direct_audio = await b.tts_synthesize(direct_text, ctx=ctx)

    sink = LogSink(gateway_log=tmp_path / "g.log")
    tr = FakeTransport()
    sess = Session(VoiceSession(session_id="s", device_id="d"), tr, b, sink)
    runner = asyncio.create_task(sess.run())
    tr.push_utterance("ping")
    while not tr.sent:
        await asyncio.sleep(0.005)
    assert tr.sent[0] == direct_audio  # adapter introduces no transformation
    tr.end_stream()
    await asyncio.wait_for(runner, timeout=2)


async def test_sc006_control_plane_works_with_no_active_call(tmp_path):
    """Management plane fully functional without any WebRTC session up
    (constitution III / SC-006)."""
    svc = ManagementService(
        Registry(), LogSink(gateway_log=tmp_path / "g.log"), SatelliteAdapterConfig()
    )
    svc.register({"device_id": "d1", "device_type": "browser"})
    assert svc.heartbeat("d1") is True
    assert svc.list_clients()[0]["webrtc_state"] == "none"  # no call, still serving
    assert svc.get_state("d1")["session"] is None
