"""US4 (P3): dropped connection recovers without operator action / restart."""

import asyncio

import pytest

from satellite_core.logsink import LogSink
from satellite_core.models import VoiceSession
from satellite_core.registry import Registry
from satellite_core.webrtc.session import Session
from satellite_core.webrtc.signaling import SignalingService

pytestmark = pytest.mark.asyncio


async def test_transport_drop_ends_session_cleanly(tmp_path, bridge):
    from fakes import FakeTransport

    sink = LogSink(gateway_log=tmp_path / "g.log")
    tr = FakeTransport()
    sess = Session(VoiceSession(session_id="s1", device_id="d"), tr, bridge, sink)
    runner = asyncio.create_task(sess.run())
    await asyncio.sleep(0.02)
    tr.drop()  # ICE/connection lost
    await asyncio.wait_for(runner, timeout=2)
    assert tr.closed


async def test_reoffer_after_drop_without_restart(tmp_path, bridge):
    from fakes import FakeTransport

    reg = Registry()
    sink = LogSink(gateway_log=tmp_path / "g.log")

    async def factory(sdp, device_id):
        return ("ANSWER", FakeTransport())

    sig = SignalingService(reg, bridge, sink, factory)

    await sig.handle_offer({"sdp": "o", "device_id": "d1", "device_type": "browser"})
    first = sig.status("d1")["session_id"]
    await sig.drop("d1")
    assert sig.status("d1") is None

    # same process, no restart: a fresh offer establishes a new session
    await sig.handle_offer({"sdp": "o2", "device_id": "d1", "device_type": "browser"})
    second = sig.status("d1")
    assert second is not None and second["session_id"] != first
