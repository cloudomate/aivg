"""Per-session log sink → Hermes's EXISTING gateway.log stream.

Constitution Principle IV: reuse ``~/.hermes/logs/gateway.log``; do not invent
a separate log store. An in-memory ring buffer backs the logs SSE endpoints
(design Appendix A) and dashboard WS fan-out.
"""

from __future__ import annotations

import json
import os
from collections import deque
from pathlib import Path
from typing import Callable, Deque, Iterable

from .models import LogEntry, LogLevel, LogSource

GATEWAY_LOG_PATH = Path(os.path.expanduser("~/.hermes/logs/gateway.log"))


class LogSink:
    def __init__(self, capacity: int = 2000, gateway_log: Path | None = None) -> None:
        self._buf: Deque[LogEntry] = deque(maxlen=capacity)
        self._gateway_log = gateway_log if gateway_log is not None else GATEWAY_LOG_PATH
        self._subscribers: list[Callable[[LogEntry], None]] = []

    def subscribe(self, cb: Callable[[LogEntry], None]) -> Callable[[], None]:
        self._subscribers.append(cb)
        return lambda: self._subscribers.remove(cb) if cb in self._subscribers else None

    def emit(
        self,
        device_id: str,
        level: LogLevel,
        source: LogSource,
        message: str,
        metadata: dict | None = None,
    ) -> LogEntry:
        entry = LogEntry(
            device_id=device_id,
            level=level,
            source=source,
            message=message,
            metadata=metadata,
        )
        self._buf.append(entry)
        self._append_gateway_log(entry)
        for cb in list(self._subscribers):
            try:
                cb(entry)
            except Exception:  # never let a subscriber break logging
                pass
        return entry

    def _append_gateway_log(self, e: LogEntry) -> None:
        try:
            self._gateway_log.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(
                {
                    "ts": e.timestamp,
                    "device_id": e.device_id,
                    "level": e.level.value,
                    "source": e.source.value,
                    "msg": e.message,
                    "meta": e.metadata,
                }
            )
            with self._gateway_log.open("a") as fh:
                fh.write(line + "\n")
        except OSError:
            # Gateway log unavailable must not crash the voice path.
            pass

    def query(
        self,
        *,
        device_id: str | None = None,
        level: str | None = None,
        source: str | None = None,
        since: float | None = None,
    ) -> Iterable[LogEntry]:
        for e in list(self._buf):
            if device_id and e.device_id != device_id:
                continue
            if level and e.level.value != level:
                continue
            if source and e.source.value != source:
                continue
            if since is not None and e.timestamp < since:
                continue
            yield e
