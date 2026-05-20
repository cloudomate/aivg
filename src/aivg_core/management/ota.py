"""OTA service (feature 011 T066, R-6).

Single ``OtaService`` API:

* :meth:`load_manifest(device_type)` — read
  ``~/.aivg/firmware/<device_type>/manifest.json``; the only place
  per-``device_type`` branching is allowed (constitution II sanctioned
  divergence: browser is OTA-exempt).
* :meth:`check(client)` — has-update? based on the manifest version vs
  the client's reported ``firmware_version``.
* :meth:`apply(client, version, url)` — create an :class:`OtaJob`,
  broadcast the ``ota_apply`` frame to the device WS, mark
  ``client.ota_state = downloading``.
* :meth:`status_report(client, body)` — device-reported transition;
  updates ``client.ota_state`` and emits a log entry with
  ``source="ota"`` so the existing SSE log stream carries OTA progress
  (R-3, T068).
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from ..logsink import LogSink
from ..models import (
    ConnectedClient,
    LogLevel,
    LogSource,
    OtaJob,
    OtaManifest,
    OtaState,
)

DEFAULT_FIRMWARE_DIR = Path("~/.aivg/firmware").expanduser()


class BrowserNotOtaEligible(RuntimeError):
    """Raised when an OTA endpoint is called on a browser device.

    Browser-no-OTA is the one sanctioned per-type divergence
    (constitution II).
    """


class OtaService:
    """OTA orchestration. Persists per-device state on the
    :class:`ConnectedClient` and emits progress events through the
    in-process :class:`LogSink` so the existing SSE stream relays them.
    """

    def __init__(
        self,
        sink: LogSink,
        *,
        firmware_dir: Optional[Path] = None,
        broadcast: Optional[Callable[[dict], None]] = None,
    ) -> None:
        self._sink = sink
        self._firmware_dir = firmware_dir or DEFAULT_FIRMWARE_DIR
        self._broadcast = broadcast or (lambda _msg: None)
        self._jobs: dict[str, OtaJob] = {}  # device_id → active job

    # --- manifest -------------------------------------------------------

    def load_manifest(self, device_type: str) -> OtaManifest:
        if device_type == "browser":
            raise BrowserNotOtaEligible(
                "browser devices are not OTA-eligible "
                "(constitution II sanctioned divergence)"
            )
        path = self._firmware_dir / device_type / "manifest.json"
        if not path.exists():
            raise FileNotFoundError(
                f"no firmware manifest for device_type {device_type!r} "
                f"at {path}"
            )
        data = json.loads(path.read_text())
        # OtaManifest's __post_init__ validates sha256 + browser rejection.
        return OtaManifest(
            device_type=data.get("device_type", device_type),
            version=data["version"],
            url=data["url"],
            sha256=data["sha256"],
            signature=data.get("signature"),
            changelog=data.get("changelog", ""),
        )

    # --- operator-facing actions ----------------------------------------

    def check(self, client: ConnectedClient) -> tuple[int, dict[str, Any]]:
        if client.device_type == "browser":
            return 409, {
                "error": "browser_not_ota_eligible",
                "message": "browser devices have no firmware to update",
            }
        try:
            manifest = self.load_manifest(client.device_type)
        except FileNotFoundError as e:
            return 404, {"error": "unknown_device", "message": str(e)}

        update_available = manifest.version != client.firmware_version
        return 200, {
            "update_available": update_available,
            "current_version": client.firmware_version,
            "latest_version": manifest.version if update_available else None,
            "changelog_url": None,  # in v1 changelog is inline, not URL
        }

    def apply(
        self,
        client: ConnectedClient,
        version: str,
        url: Optional[str] = None,
    ) -> tuple[int, dict[str, Any]]:
        if client.device_type == "browser":
            return 409, {
                "error": "browser_not_ota_eligible",
                "message": "browser devices are not OTA-eligible",
            }
        # In-progress guard.
        if client.device_id in self._jobs and self._jobs[client.device_id].state not in (
            OtaState.IDLE,
            OtaState.FAILED,
            OtaState.ROLLED_BACK,
        ):
            return 409, {
                "error": "ota_in_progress",
                "message": f"device {client.device_id!r} already has an OTA in flight",
            }
        try:
            manifest = self.load_manifest(client.device_type)
        except FileNotFoundError as e:
            return 404, {"error": "unknown_device", "message": str(e)}

        job = OtaJob(
            job_id=uuid.uuid4().hex,
            device_id=client.device_id,
            target_version=version,
            state=OtaState.DOWNLOADING,
            started_at=time.time(),
        )
        self._jobs[client.device_id] = job
        client.ota_state = OtaState.DOWNLOADING
        client.ota_version = version
        client.ota_job_id = job.job_id
        # Push to the device over the always-on control WS.
        self._broadcast(
            {
                "type": "ota_apply",
                "device_id": client.device_id,
                "version": version,
                "url": url or manifest.url,
                "sha256": manifest.sha256,
            }
        )
        self._sink.emit(
            client.device_id,
            LogLevel.INFO,
            LogSource.OTA,
            f"ota_apply target_version={version}",
            {"state": "downloading", "version": version, "job_id": job.job_id},
        )
        return 202, {
            "job_id": job.job_id,
            "device_id": client.device_id,
            "target_version": version,
            "state": job.state.value,
            "started_at": job.started_at,
        }

    # --- device-reported status (T068) ----------------------------------

    def status_report(
        self,
        client: ConnectedClient,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        try:
            new_state = OtaState(body["state"])
        except (KeyError, ValueError):
            return 400, {
                "error": "bad_input",
                "message": f"invalid OTA state: {body.get('state')!r}",
            }
        client.ota_state = new_state
        if new_state in (OtaState.FAILED, OtaState.ROLLED_BACK):
            result = new_state.value
            reason = body.get("failure_reason") or "(unspecified)"
        elif new_state == OtaState.IDLE and body.get("result") == "success":
            result = "success"
            reason = None
            client.firmware_version = body.get("version", client.firmware_version)
        else:
            result = None
            reason = None

        job = self._jobs.get(client.device_id)
        if job is not None:
            job.state = new_state
            if result is not None:
                job.ended_at = time.time()
                job.result = result
                job.failure_reason = reason

        # Relay through LogSink so the SSE stream picks it up.
        self._sink.emit(
            client.device_id,
            LogLevel.INFO if result != "failed" and new_state != OtaState.FAILED else LogLevel.ERROR,
            LogSource.OTA,
            f"ota_status state={new_state.value}"
            + (f" result={result}" if result else ""),
            {
                "state": new_state.value,
                "version": body.get("version"),
                "result": result,
                "failure_reason": reason,
                "job_id": job.job_id if job else None,
            },
        )
        return 204, {}

    # --- read accessors -------------------------------------------------

    def get_job(self, device_id: str) -> Optional[OtaJob]:
        return self._jobs.get(device_id)

    def manifest_response(self, client: ConnectedClient) -> tuple[int, dict[str, Any]]:
        if client.device_type == "browser":
            return 409, {
                "error": "browser_not_ota_eligible",
                "message": "browser devices are not OTA-eligible",
            }
        try:
            m = self.load_manifest(client.device_type)
        except FileNotFoundError as e:
            return 404, {"error": "unknown_device", "message": str(e)}
        return 200, {
            "device_type": m.device_type,
            "version": m.version,
            "url": m.url,
            "sha256": m.sha256,
            "signature": m.signature,
            "changelog": m.changelog,
        }
