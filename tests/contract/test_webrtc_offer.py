"""Contract: POST /webrtc/offer (contracts/webrtc-signaling.md).

The client is the offerer; the adapter answers and binds a VoiceSession.
SDP shape (one audio m-line, no video, Opus 48 kHz, no munging) is enforced by
aiortc in production; here we assert the signaling-contract behaviour with an
injected transport factory.
"""

import pytest

from satellite_core.config import SatelliteAdapterConfig
from satellite_core.logsink import LogSink
from satellite_core.registry import Registry
from satellite_core.webrtc.signaling import SignalingService

pytestmark = pytest.mark.asyncio


async def _factory(offer_sdp, device_id):
    from fakes import FakeTransport

    return ("v=0\r\nANSWER-SDP", FakeTransport())


async def test_offer_returns_answer_and_opens_session(tmp_path, bridge):
    reg = Registry()
    sink = LogSink(gateway_log=tmp_path / "g.log")
    sig = SignalingService(reg, bridge, sink, _factory)

    res = await sig.handle_offer(
        {"sdp": "v=0 OFFER", "type": "offer", "device_id": "browser-1",
         "device_type": "browser"}
    )
    assert res["type"] == "answer"
    assert "ANSWER-SDP" in res["sdp"]

    status = sig.status("browser-1")
    assert status is not None and status["state"] in ("listening", "idle")
    await sig.drop("browser-1")
    assert sig.status("browser-1") is None
