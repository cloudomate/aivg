"""Contract: SSE log tail (feature 011 T021).

Covers the in-process SSE iterator behavior (framing, filters,
live-emit). The HTTP-level test belongs in an integration phase once an
aiohttp test client is wired; for v1 we verify the iterator directly.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from aivg_core.logsink import LogSink
from aivg_core.management.log_sse import sse_logs
from aivg_core.models import LogLevel, LogSource


def _parse(frame: str) -> dict:
    """Pull the JSON payload out of one SSE frame."""
    for line in frame.split("\n"):
        if line.startswith("data:"):
            return json.loads(line[len("data:"):].strip())
    raise AssertionError(f"no data line in frame: {frame!r}")


@pytest.mark.asyncio
async def test_backlog_replay(tmp_path):
    sink = LogSink(gateway_log=tmp_path / "g.log")
    sink.emit("d1", LogLevel.INFO, LogSource.SYSTEM, "boot")
    sink.emit("d1", LogLevel.ERROR, LogSource.ASR, "boom")

    frames: list[str] = []
    agen = sse_logs(sink)
    # Take just the backlog (two entries) then cancel.
    for _ in range(2):
        frames.append(await agen.__anext__())
    await agen.aclose()
    assert len(frames) == 2
    msgs = [_parse(f)["message"] for f in frames]
    assert msgs == ["boot", "boom"]


@pytest.mark.asyncio
async def test_filter_by_level_and_source(tmp_path):
    sink = LogSink(gateway_log=tmp_path / "g.log")
    sink.emit("d1", LogLevel.INFO, LogSource.SYSTEM, "boot")
    sink.emit("d1", LogLevel.ERROR, LogSource.ASR, "boom")
    sink.emit("d1", LogLevel.INFO, LogSource.OTA, "downloading")

    agen = sse_logs(sink, level="ERROR")
    frame = await agen.__anext__()
    await agen.aclose()
    assert _parse(frame)["source"] == "asr"

    agen = sse_logs(sink, source="ota")
    frame = await agen.__anext__()
    await agen.aclose()
    assert _parse(frame)["message"] == "downloading"


@pytest.mark.asyncio
async def test_live_emission_after_backlog(tmp_path):
    sink = LogSink(gateway_log=tmp_path / "g.log")
    sink.emit("d1", LogLevel.INFO, LogSource.SYSTEM, "first")

    agen = sse_logs(sink)
    backlog = await agen.__anext__()
    assert _parse(backlog)["message"] == "first"

    # Live emit should produce a new frame promptly.
    sink.emit("d1", LogLevel.INFO, LogSource.SYSTEM, "second")
    live = await asyncio.wait_for(agen.__anext__(), timeout=1.0)
    await agen.aclose()
    assert _parse(live)["message"] == "second"


@pytest.mark.asyncio
async def test_frame_includes_event_id(tmp_path):
    sink = LogSink(gateway_log=tmp_path / "g.log")
    sink.emit("d1", LogLevel.INFO, LogSource.SYSTEM, "hello")
    agen = sse_logs(sink)
    frame = await agen.__anext__()
    await agen.aclose()
    assert "id: " in frame
    assert "event: log_entry" in frame
