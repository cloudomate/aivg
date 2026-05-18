"""US2 (P2): barge-in stops playback ≤300 ms (SC-003), no overlapping reply."""

import asyncio

import pytest

from hermes_satellite_adapter.logsink import LogSink
from hermes_satellite_adapter.models import VoiceSession
from hermes_satellite_adapter.session import Session

pytestmark = pytest.mark.asyncio


async def test_speech_during_reply_cancels_and_next_turn_wins(tmp_path):
    from fakes import SPEECH, FakeHermesBridge, FakeTransport

    sink = LogSink(gateway_log=tmp_path / "g.log")
    tr = FakeTransport()
    # Slow TTS so the user can interrupt while "speaking".
    bridge = FakeHermesBridge(tts_latency=0.5)
    sess = Session(VoiceSession(session_id="s1", device_id="d"), tr, bridge, sink)
    runner = asyncio.create_task(sess.run())

    tr.push_utterance("first question")
    await asyncio.sleep(0.05)  # let it reach THINKING/SPEAKING
    tr.push(SPEECH)            # user barges in

    # interrupting turn should be cancelled promptly
    for _ in range(200):
        if tr.stop_calls:
            break
        await asyncio.sleep(0.005)
    assert tr.stop_calls >= 1
    assert tr.sent == []  # first reply never played (interrupted, no overlap)

    barge_logs = [
        e for e in sink.query() if e.message == "barge-in" and e.metadata
    ]
    assert barge_logs and barge_logs[-1].metadata["stop_ms"] < 300  # SC-003

    # the next utterance is handled as a fresh turn
    tr.push_utterance("second question")
    for _ in range(400):
        if tr.sent:
            break
        await asyncio.sleep(0.005)
    assert tr.sent == [b"AUDIO:echo: second question"]

    tr.end_stream()
    await asyncio.wait_for(runner, timeout=2)
