"""Streaming helpers for ``sat-cli`` follow modes (logs, watch).

Owns the iteration-and-emission glue between :class:`ManagementClient`
SSE iterators and the JSON-envelope output writer.
"""

from __future__ import annotations

from typing import AsyncIterator

from .output import emit_ndjson, human_log_entry, context


async def stream_log_entries(stream: AsyncIterator[dict]) -> None:
    """Consume an SSE log stream and emit each entry on stdout in the
    active output mode."""
    ctx = context()
    async for entry in stream:
        if ctx.json_mode:
            emit_ndjson(entry)
        else:
            human_log_entry(entry)
