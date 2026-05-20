"""SSE iterator over :class:`aivg_core.logsink.LogSink` (feature 011 T026).

Emits one ``data: {json}\\n\\n`` line per :class:`LogEntry`. First yields
the buffered backlog matching the filters, then live-subscribes for new
entries until the consumer disconnects. Each entry is also prefixed with
an ``id: <ts>:<seq>`` line so SSE ``Last-Event-Id`` can resume.

OTA progress is delivered on the same stream as ``source="ota"`` (feature
011 R-3, R-6); ``sat-cli ota apply --follow`` consumes this directly.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
from typing import AsyncIterator, Optional

from ..logsink import LogSink
from ..models import LogEntry


def _entry_to_json(e: LogEntry) -> dict:
    return {
        "device_id": e.device_id,
        "timestamp": e.timestamp,
        "level": e.level.value,
        "source": e.source.value,
        "message": e.message,
        "metadata": e.metadata,
    }


def _matches(
    e: LogEntry,
    *,
    device_id: Optional[str],
    level: Optional[str],
    source: Optional[str],
    since: Optional[float],
) -> bool:
    if device_id and e.device_id != device_id:
        return False
    if level and e.level.value != level:
        return False
    if source and e.source.value != source:
        return False
    if since is not None and e.timestamp < since:
        return False
    return True


async def sse_logs(
    sink: LogSink,
    *,
    device_id: Optional[str] = None,
    level: Optional[str] = None,
    source: Optional[str] = None,
    since: Optional[float] = None,
    backlog: bool = True,
    queue_size: int = 256,
) -> AsyncIterator[str]:
    """Async iterator of SSE-framed lines.

    Subscribe-first to avoid the race where a new entry arrives between
    backlog replay and live subscription: we snapshot the buffer's
    current entries (by object identity) and have the subscriber skip
    any entry already in that snapshot. Then we replay the snapshot, and
    finally start consuming the live queue.
    """
    seq = 0

    def _frame(e: LogEntry) -> str:
        nonlocal seq
        seq += 1
        payload = json.dumps(_entry_to_json(e), separators=(",", ":"))
        return f"id: {e.timestamp:.6f}:{seq}\nevent: log_entry\ndata: {payload}\n\n"

    loop = asyncio.get_event_loop()
    queue: asyncio.Queue[LogEntry] = asyncio.Queue(maxsize=queue_size)
    # Snapshot the buffer NOW so subscriber dedup is precise.
    snapshot_ids = {id(e) for e in list(sink._buf)}  # noqa: SLF001

    def _push(e: LogEntry) -> None:
        if id(e) in snapshot_ids:
            return  # already counted in backlog replay
        if not _matches(e, device_id=device_id, level=level, source=source, since=since):
            return
        try:
            loop.call_soon_threadsafe(queue.put_nowait, e)
        except (asyncio.QueueFull, RuntimeError):
            pass  # drop on overflow rather than block the producer

    unsubscribe = sink.subscribe(_push)
    try:
        # Backlog replay from the snapshot taken above.
        if backlog:
            for e in sink.query(
                device_id=device_id, level=level, source=source, since=since
            ):
                if id(e) in snapshot_ids:
                    yield _frame(e)
        # Live tail.
        while True:
            entry = await queue.get()
            yield _frame(entry)
    finally:
        unsubscribe()
