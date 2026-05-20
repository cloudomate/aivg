"""US2 T026: call-scoped UI event emitter (the SCTP-datachannel logic side).

Asserts the emitter carries ONLY call-scoped UI (state / partial transcript /
barge-in) and never durable control (constitution III).
"""

import asyncio

import pytest

from aivg_core.logsink import LogSink
from aivg_core.models import VoiceSession
from aivg_core.webrtc.session import Session

pytestmark = pytest.mark.asyncio


async def test_ui_sink_emits_state_and_transcript(tmp_path, bridge, transport):
    events = []
    sink = LogSink(gateway_log=tmp_path / "g.log")
    sess = Session(
        VoiceSession(session_id="s1", device_id="d"),
        transport,
        bridge,
        sink,
        ui_sink=events.append,
    )
    runner = asyncio.create_task(sess.run())
    transport.push_utterance("hello there")
    while not transport.sent:
        await asyncio.sleep(0.005)
    transport.end_stream()
    await asyncio.wait_for(runner, timeout=2)

    kinds = [e["type"] for e in events]
    assert "state" in kinds and "partial_transcript" in kinds
    states = [e["state"] for e in events if e["type"] == "state"]
    assert {"listening", "thinking", "speaking"}.issubset(set(states))
    tx = next(e for e in events if e["type"] == "partial_transcript")
    assert tx["text"] == "hello there"
    # ONLY call-scoped UI kinds — no durable control leaks here (constitution III)
    assert set(kinds) <= {"state", "partial_transcript", "barge_in"}
    assert all(e["session_id"] == "s1" for e in events)
