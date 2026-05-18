"""HermesV013Bridge logic that is testable WITHOUT the hermes package:
the VG-2 silence rule and the VG-3 agent_runner bridging. The STT/TTS paths
are host-only (lazy hermes imports) and covered by the live smoke (T045).
"""

import array

import pytest

from hermes_satellite_adapter.hermes_bridge import HermesV013Bridge, SessionCtx

pytestmark = pytest.mark.asyncio


def _pcm(value: int, n: int = 200) -> bytes:
    return array.array("h", [value] * n).tobytes()


async def _one(frame: bytes):
    yield frame


async def test_detect_endpoint_applies_rms_and_duration_rule():
    # frame_seconds=0.5 → speech-confirm after 1 loud frame (>=0.3s),
    # end after 6 silent frames (>=3.0s) using the default RMS<200 rule.
    b = HermesV013Bridge(frame_seconds=0.5)
    ctx = SessionCtx(device_id="d", session_id="s")

    sig = await b.detect_endpoint(_one(_pcm(6000)), ctx=ctx)
    assert sig.speech_started is True and sig.end_of_utterance is False

    end = False
    for _ in range(6):  # 6 * 0.5s = 3.0s of silence
        sig = await b.detect_endpoint(_one(_pcm(0)), ctx=ctx)
        end = end or sig.end_of_utterance
    assert end is True
    # state reset after end → a new utterance needs fresh speech-confirm
    sig = await b.detect_endpoint(_one(_pcm(0)), ctx=ctx)
    assert sig.speech_started is False


async def test_quiet_audio_below_threshold_is_silence():
    b = HermesV013Bridge(frame_seconds=0.5)
    ctx = SessionCtx(device_id="d", session_id="s2")
    sig = await b.detect_endpoint(_one(_pcm(50)), ctx=ctx)  # RMS 50 < 200
    assert sig.speech_started is False and sig.end_of_utterance is False


async def test_agent_turn_uses_injected_gateway_runner():
    seen = {}

    async def runner(text, ctx):
        seen["text"] = text
        return "reply: " + text

    b = HermesV013Bridge(agent_runner=runner)
    ctx = SessionCtx(device_id="d", session_id="s")
    r = await b.agent_turn("hello", ctx=ctx)
    assert r.text == "reply: hello" and r.is_empty is False
    assert seen["text"] == "hello"


async def test_agent_turn_empty_input_is_empty_reply():
    async def runner(text, ctx):  # pragma: no cover - not reached
        return "x"

    b = HermesV013Bridge(agent_runner=runner)
    r = await b.agent_turn("   ", ctx=SessionCtx(device_id="d", session_id="s"))
    assert r.is_empty is True and r.text == ""


async def test_agent_turn_without_runner_raises_clear_gate_error():
    b = HermesV013Bridge()
    with pytest.raises(NotImplementedError, match="agent_runner not injected"):
        await b.agent_turn("hi", ctx=SessionCtx(device_id="d", session_id="s"))
