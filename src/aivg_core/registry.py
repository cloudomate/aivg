"""In-memory client + session registry (process lifetime, no database).

Device-agnostic: ``device_type`` is stored for telemetry only and MUST NOT
drive protocol branching (constitution Principle II).

Feature 011 adds a ``_pending`` lifecycle for unclaimed devices (R-7).
Adopted clients live in ``_clients``; pending devices in ``_pending``.
A ``device_id`` is uniquely in one of the two.
"""

from __future__ import annotations

import time
import uuid
from typing import Callable, Optional

from .models import (
    AdoptionState,
    ClientStatus,
    ConnectedClient,
    PendingDevice,
    SatelliteConfig,
    SessionState,
    VoiceSession,
)


class Registry:
    def __init__(self) -> None:
        self._clients: dict[str, ConnectedClient] = {}
        self._pending: dict[str, PendingDevice] = {}
        self._sessions: dict[str, VoiceSession] = {}
        # Optional persistence hook (feature 011 T014). Called after any
        # mutation that affects adopted clients.
        self._persist_hook: Optional[Callable[["Registry"], None]] = None
        # Queued config writes (feature 011 US3 FR-016) — applied on the
        # next register or heartbeat for offline devices.
        self._queued_writes: dict[str, dict] = {}

    def attach_persist_hook(self, hook: Callable[["Registry"], None]) -> None:
        self._persist_hook = hook

    def _persist(self) -> None:
        if self._persist_hook is not None:
            try:
                self._persist_hook(self)
            except Exception:  # noqa: BLE001 - persistence failures must not crash mutation
                pass

    # --- registration & adoption ----------------------------------------
    def register(
        self,
        device_id: str,
        device_type: str,
        *,
        firmware_version: str = "",
        ip_address: str = "",
        config: SatelliteConfig | None = None,
        factory_reset: bool = False,
    ) -> ConnectedClient:
        """Backwards-compatible register.

        Today this is the direct-adopt path used by the voice plane and by
        feature 001's existing register endpoint. Feature 011 US2 will
        introduce a separate ``register_pending`` call for the new
        Improv-onboarding flow; this method keeps current behavior so the
        voice loop and prior tests stay green.

        ``factory_reset=True`` on an adopted id → drop the client (R-7);
        the next register re-creates it.
        """
        if factory_reset:
            self._clients.pop(device_id, None)
            self._persist()

        client = self._clients.get(device_id)
        if client is None:
            client = ConnectedClient(
                device_id=device_id,
                device_type=device_type,
                adoption_state=AdoptionState.ADOPTED,
                name=device_id,  # pre-feature-011 callers had no separate name
            )
            self._clients[device_id] = client
        client.device_type = device_type
        client.firmware_version = firmware_version
        client.ip_address = ip_address
        if config is not None:
            client.config = config
        client.status = ClientStatus.ONLINE
        client.last_error = None
        client.touch()
        self._flush_queued_writes(client)  # apply any offline-queued config (US3)
        self._persist()
        return client

    def register_pending(
        self,
        device_id: str,
        device_type: str,
        *,
        firmware_version: str = "",
        ip_address: str = "",
    ) -> PendingDevice:
        """Feature 011 US2 onboarding entry. The device shows up unclaimed
        and must be promoted via :meth:`adopt`. If an adopted record
        already exists for this id, raises (use ``register(...,
        factory_reset=True)`` to demote)."""
        if device_id in self._clients:
            raise RuntimeError(f"already_adopted: {device_id!r}")
        pending = self._pending.get(device_id)
        if pending is None:
            pending = PendingDevice(
                device_id=device_id,
                device_type=device_type,
                firmware_version=firmware_version,
                ip_address=ip_address,
            )
            self._pending[device_id] = pending
        else:
            pending.device_type = device_type
            pending.firmware_version = firmware_version
            pending.ip_address = ip_address
            pending.touch()
        return pending

    # --- demotion (factory_reset path, T047) ----------------------------
    def demote_to_pending(
        self,
        device_id: str,
        *,
        device_type: str,
        firmware_version: str = "",
        ip_address: str = "",
    ) -> PendingDevice:
        """An adopted device announces ``factory_reset=True`` on register:
        drop the persisted client record and re-create as pending so the
        operator must re-claim it (R-7)."""
        if device_id in self._clients:
            c = self._clients.pop(device_id)
            if c.active_session_id:
                self._sessions.pop(c.active_session_id, None)
            self._persist()
        return self.register_pending(
            device_id=device_id,
            device_type=device_type,
            firmware_version=firmware_version,
            ip_address=ip_address,
        )

    # --- adoption (US2 entry point) -------------------------------------
    def list_pending(self) -> list[PendingDevice]:
        return list(self._pending.values())

    def get_pending(self, device_id: str) -> Optional[PendingDevice]:
        return self._pending.get(device_id)

    def adopt(
        self,
        device_id: str,
        *,
        name: str,
        default_config: Optional[SatelliteConfig] = None,
        device_limit: int = 10,
    ) -> ConnectedClient:
        """Promote a pending device to adopted.

        Raises:
            KeyError: no pending device with that id.
            RuntimeError: already adopted, or the fleet is at its limit.
        """
        if device_id in self._clients:
            raise RuntimeError(f"already_adopted: {device_id!r}")
        if len(self._clients) >= device_limit:
            raise RuntimeError(
                f"device_limit_reached: current={len(self._clients)} limit={device_limit}"
            )
        pending = self._pending.pop(device_id, None)
        if pending is None:
            raise KeyError(f"unknown_pending_device: {device_id!r}")
        client = ConnectedClient(
            device_id=device_id,
            device_type=pending.device_type,
            firmware_version=pending.firmware_version,
            ip_address=pending.ip_address,
            config=default_config or SatelliteConfig(),
            status=ClientStatus.ONLINE,
            name=name.strip(),
            adoption_state=AdoptionState.ADOPTED,
        )
        client.touch()
        self._clients[device_id] = client
        self._persist()
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
            self._flush_queued_writes(c)
        return c

    # --- queued config writes (feature 011 US3 FR-016) ------------------
    def queue_config_write(self, device_id: str, overrides: dict) -> None:
        """Stash a config patch for an offline device; applied on the
        next register/heartbeat. Subsequent writes overwrite earlier
        queued writes for the same device (latest-pending-wins)."""
        self._queued_writes[device_id] = overrides

    def has_queued_write(self, device_id: str) -> bool:
        return device_id in self._queued_writes

    def _flush_queued_writes(self, client: ConnectedClient) -> None:
        """Apply a pending offline-write for ``client``, if any.
        Bumps ``config_version`` exactly once even if the device flapped
        between register and heartbeat."""
        pending = self._queued_writes.pop(client.device_id, None)
        if pending is None:
            return
        client.config = client.config.merged(pending)
        client.config_version += 1
        client.config_updated_at = time.time()
        self._persist()

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
