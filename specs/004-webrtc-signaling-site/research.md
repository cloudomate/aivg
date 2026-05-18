# Phase 0 Research: Serve the WebRTC Signaling Site & Redeploy

No NEEDS CLARIFICATION. Scope was given verbatim; the change site and the
deploy mechanism were already verified (feature 003). Phase 0 = pin the exact
defect and the minimal fix.

## Defect (confirmed by reading `src/hermes_satellite_adapter/adapter.py`)

`adapter.start()` builds `build_management_app(self.management)` and starts a
single `web.TCPSite` on `management_port`. The WebRTC signaling site is only a
comment: `# The WebRTC signaling site (:webrtc_port) is wired identically …`.
Result on the deployed gateway (feature 003): port 8643 listens, 8644 does
not, so `POST /webrtc/offer` is unreachable and no voice session can start.
The fake-transport test suite never caught it because those tests drive
`Session`/`SignalingService` directly and never start the aiohttp sites.

## D1 — `build_signaling_app()` mirrors `build_management_app()`

- **Decision**: Add `build_signaling_app(service: SignalingService)` to
  `signaling.py`, lazy-importing `aiohttp` exactly like `build_management_app`.
  Routes: `POST /webrtc/offer` → `await service.handle_offer(json)`;
  `POST /webrtc/candidate` → 204 (LAN fallback per feature 001 contract);
  `GET /webrtc/status/{device_id}` → `service.status(...)` (404 if none).
- **Rationale**: `SignalingService.handle_offer/status/drop` already exist and
  are tested with fakes; only the HTTP surface is missing. Reusing the proven
  management-app pattern (constitution IV) minimises risk.
- **Alternatives considered**: one combined app on a single port (rejected —
  violates constitution III / FR-003, would force gateway protocol-branching);
  a separate framework (rejected — aiohttp already in use).

## D2 — `adapter.start()` brings up both sites, ready-gated

- **Decision**: Build+start the management site, then the signaling site on
  `webrtc_port`; append BOTH runners to `self._sites`. If the signaling site
  fails to start (port in use, etc.), **tear down the already-started
  management site and raise** so the gateway never reports the adapter
  ready/connected in a control-up/signaling-down state (FR-005/SC-005).
- **Rationale**: Encodes the feature-003 lesson as enforced behaviour — a
  half-up adapter must be a hard failure, not a silent partial. `stop()`
  already cleans every runner in `self._sites`, so FR-004 holds once both are
  appended.
- **Alternatives considered**: start signaling best-effort and log a warning
  (rejected — that *is* the silent-recurrence failure FR-005 forbids); a
  separate readiness flag polled elsewhere (rejected — raising is the
  simplest, loudest, and is what the gateway plugin loader already surfaces).

## D3 — Redeploy via feature 003's existing gated path (T027)

- **Decision**: Reuse `deploy/deploy-to-hermes.sh` unchanged for the gated,
  backup-first, confirmed redeploy; it rsyncs the updated
  `hermes_satellite_adapter` package + plugin shim and restarts. **Extend only
  its `postverify()`** to additionally assert both `management_port` and
  `webrtc_port` are listening on the host (SC-001) — added to, not replacing,
  the existing constitution-I and SC-005 checks. `rollback.sh` remains the
  tested undo (SC-004).
- **Rationale**: FR-006 — no new deploy mechanism; the safe path already
  exists and is proven. The both-ports assertion makes the fix verifiable at
  deploy time and prevents a regressed redeploy from passing.
- **Alternatives considered**: a fresh deploy script (rejected — FR-006 / DRY);
  manual host edits (rejected — bypasses backup/confirm/rollback posture).

## D4 — Test strategy

- **Decision**: Keep feature 001's 34-test fake suite green (unchanged). Add
  `tests/unit/test_adapter_sites.py`: assert `build_signaling_app` is callable
  and the `SignalingService` route targets exist; assert `start()` would
  register two runners and that the signaling-bind-failure path raises after
  tearing down the management runner — using a fake `aiohttp.web` shim (no
  real aiohttp locally). Real both-ports binding is proven on the host by the
  extended deploy post-verify (SC-001).
- **Rationale**: Locally `aiohttp` isn't installed; the lifecycle/teardown
  logic is the regression-prone part and is unit-testable with a shim. Binding
  reality belongs to the host verification (constitution V).
- **Alternatives considered**: install aiohttp locally just to bind in tests
  (rejected — heavy; host post-verify already covers real binding).

**No NEEDS CLARIFICATION remain.**
