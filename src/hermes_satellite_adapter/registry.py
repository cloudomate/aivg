"""In-memory client + session registry (process lifetime, no database).

Device-agnostic: ``device_type`` is stored for telemetry only and MUST NOT
drive protocol branching (constitution Principle II).
"""

from __future__ import annotations

import time
import uuid
from typing import Optional

from .models import ClientStatus, ConnectedClient, SatelliteConfig, SessionState, VoiceSession


class Registry:
    def __init__(self) -> None:
        self._clients: dict[str, ConnectedClient] = {}
        self._sessions: dict[str, VoiceSession] = {}

    # --- clients ---------------------------------------------------------
    def register(
        self,
        device_id: str,
        device_type: str,
        *,
        firmware_version: str = "",
        ip_address: str = "",
        config: SatelliteConfig | None = None,
    ) -> ConnectedClient:
        client = self._clients.get(device_id)
        if client is None:
            client = ConnectedClient(device_id=device_id, device_type=device_type)
            self._clients[device_id] = client
        client.device_type = device_type
        client.firmware_version = firmware_version
        client.ip_address = ip_address
        if config is not None:
            client.config = config
        client.status = ClientStatus.ONLINE
        client.last_error = None
        client.touch()
        return client

    def get_client(self, device_id: str) -> Optional[ConnectedClient]:
        return self._clients.get(device_id)

    def list_clients(self) -> list[ConnectedClient]:
        return list(self._clients.values())

    def remove_client(self, device_id: str) -> bool:
        c = self._clients.pop(device_id, None)
        if c and c.active_session_id:
            self._sessions.pop(c.active_session_id, None)
        return c is not None

    def heartbeat(self, device_id: str) -> Optional[ConnectedClient]:
        c = self._clients.get(device_id)
        if c:
            c.status = ClientStatus.ONLINE
            c.touch()
        return c

    def mark_stale(self, *, now: float | None = None) -> list[ConnectedClient]:
        """Flip clients to OFFLINE if heartbeats lapsed (>3x interval). Entry
        is retained so the client can re-register (FR-014)."""
        now = now if now is not None else time.time()
        flipped = []
        for c in self._clients.values():
            if c.status == ClientStatus.ONLINE:
                if now - c.last_seen > 3 * max(1, c.config.heartbeat_interval):
                    c.status = ClientStatus.OFFLINE
                    flipped.append(c)
        return flipped

    # --- sessions --------------------------------------------------------
    def open_session(self, device_id: str) -> VoiceSession:
        client = self._clients.get(device_id)
        if client is None:
            raise KeyError(f"unknown device_id {device_id!r}")
        if client.active_session_id:
            self._sessions.pop(client.active_session_id, None)
        sid = uuid.uuid4().hex
        sess = VoiceSession(session_id=sid, device_id=device_id, state=SessionState.LISTENING)
        self._sessions[sid] = sess
        client.active_session_id = sid
        return sess

    def get_session(self, session_id: str) -> Optional[VoiceSession]:
        return self._sessions.get(session_id)

    def session_for_device(self, device_id: str) -> Optional[VoiceSession]:
        c = self._clients.get(device_id)
        if c and c.active_session_id:
            return self._sessions.get(c.active_session_id)
        return None

    def close_session(self, session_id: str) -> None:
        sess = self._sessions.pop(session_id, None)
        if sess:
            c = self._clients.get(sess.device_id)
            if c and c.active_session_id == session_id:
                c.active_session_id = None

    def list_sessions(self) -> list[VoiceSession]:
        return list(self._sessions.values())
