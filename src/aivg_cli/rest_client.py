"""``httpx``-based REST client for the satellite management plane.

Maps network/HTTP failures onto the closed ``error.code`` set documented
in :mod:`aivg_cli.exit_codes` (R-9). All callers see the typed envelope
shape; no raw exceptions cross the public surface.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Optional

import httpx


class RestError(Exception):
    """Carries a stable ``error.code`` and an HTTP status (when available)."""

    def __init__(self, code: str, message: str, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _map_status(status: int, body: Any) -> RestError:
    if isinstance(body, dict):
        code = body.get("error") or body.get("code") or ""
        msg = body.get("message") or str(body)
        if code:
            return RestError(code, msg, status)
    if status == 404:
        return RestError("unknown_device", "not found", status)
    if status == 503:
        return RestError("device_offline", "device offline", status)
    if status == 409:
        return RestError("config_conflict", "conflict", status)
    return RestError("internal_error", f"HTTP {status}", status)


class ManagementClient:
    """One-per-process REST client. Owns a single ``httpx.AsyncClient`` so
    keep-alive + connection-pool reuse works for ``watch``/``logs follow``."""

    def __init__(self, base_url: str, *, timeout: float = 10.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "ManagementClient":
        self._client = httpx.AsyncClient(base_url=self._base, timeout=self._timeout)
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(
        self, method: str, path: str, *, json: Any = None, params: Any = None
    ) -> Any:
        assert self._client is not None, "ManagementClient must be used as async-context-manager"
        try:
            resp = await self._client.request(method, path, json=json, params=params)
        except httpx.ConnectError as e:
            raise RestError("gateway_unreachable", str(e)) from e
        except httpx.TimeoutException as e:
            raise RestError("gateway_unreachable", f"timeout: {e}") from e
        if resp.status_code == 204:
            return None
        try:
            body = resp.json()
        except ValueError:
            body = {"raw": resp.text}
        if resp.status_code >= 400:
            raise _map_status(resp.status_code, body)
        return body

    # --- REST endpoints (subset for US1 MVP) --------------------------
    async def list_devices(self, *, state: str = "all") -> list[dict]:
        return await self._request("GET", "/satellite/list", params={"state": state})

    async def get_device_state(self, device_id: str) -> dict:
        return await self._request("GET", f"/satellite/{device_id}/state")

    async def get_device_config(self, device_id: str) -> dict:
        return await self._request("GET", f"/satellite/{device_id}/config")

    async def get_fleet_logs(self, **filters: Any) -> list[dict]:
        params = {k: v for k, v in filters.items() if v is not None}
        return await self._request("GET", "/satellite/logs", params=params)

    async def follow_device_logs(
        self,
        device_id: str,
        **filters: Any,
    ) -> AsyncIterator[dict]:
        async for entry in self._follow(f"/satellite/{device_id}/logs", filters):
            yield entry

    async def follow_fleet_logs(self, **filters: Any) -> AsyncIterator[dict]:
        async for entry in self._follow("/satellite/logs", filters):
            yield entry

    async def _follow(self, path: str, filters: dict) -> AsyncIterator[dict]:
        """Stream SSE log entries as parsed dicts. Re-raises ``RestError``
        on network failure mid-stream so the CLI can exit cleanly."""
        import json

        assert self._client is not None
        params = {k: v for k, v in filters.items() if v is not None}
        params["follow"] = "true"
        try:
            async with self._client.stream(
                "GET", path, params=params, timeout=httpx.Timeout(None)
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise _map_status(resp.status_code, _try_json(body))
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if line.startswith(":"):
                        continue  # SSE comment / keepalive
                    if line.startswith("data:"):
                        try:
                            yield json.loads(line[5:].strip())
                        except ValueError:
                            continue
        except httpx.ConnectError as e:
            raise RestError("gateway_unreachable", str(e)) from e
        except httpx.TimeoutException as e:
            raise RestError("gateway_unreachable", f"timeout: {e}") from e


def _try_json(body: bytes) -> Any:
    import json

    try:
        return json.loads(body.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return {"raw": body.decode("utf-8", errors="replace")}
