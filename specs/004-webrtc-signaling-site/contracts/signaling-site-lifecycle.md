# Contract: Signaling Site & Adapter Lifecycle

Scope: how the adapter brings up/tears down its two planes and how redeploy
verifies it. The HTTP request/response shapes are NOT redefined here — they
are feature 001's `contracts/webrtc-signaling.md`, reused verbatim.

## `build_signaling_app(service: SignalingService)` — route surface

| Method / Path | Delegates to | Response |
|---------------|--------------|----------|
| `POST /webrtc/offer` | `await service.handle_offer(body)` | `{sdp,type:"answer"}` |
| `POST /webrtc/candidate` | (LAN fallback) | `204` |
| `GET /webrtc/status/{device_id}` | `service.status(device_id)` | status JSON or `404` |

Mirrors `build_management_app` (lazy `aiohttp` import; production-only path).

## Adapter start/stop contract

- `start()` with `cfg.enabled`:
  1. build+start management site on `management_port`
  2. build+start signaling site on `webrtc_port`
  3. both runners recorded for teardown
  4. **signaling bind failure ⇒ tear down management site + raise** (FR-005);
     the adapter is NOT presented as ready/connected half-up (SC-005)
- `stop()`: clean up **every** recorded runner; no orphaned listeners (FR-004)
- Planes stay on **separate ports** — never merged (FR-003 / constitution III)

## Redeploy verification (extends feature 003 `deploy-to-hermes.sh` postverify)

Existing checks kept (plugin registers; constitution-I no embedded engines;
SC-005 no pre-existing platform removed). **Added**:

- `T:` after redeploy, BOTH `management_port` AND `webrtc_port` are LISTENING
  on the host (SC-001) — fail the deploy (→ rollback hint) if either is absent.

## Conformance checks (→ tasks/tests)

- `T:` `build_signaling_app` exists; exposes the three routes above.
- `T:` `start()` registers two runners; `stop()` cleans both (FR-004).
- `T:` simulated signaling bind-failure ⇒ `start()` raises AND the management
  runner was cleaned (FR-005/SC-005) — no half-up.
- `T:` feature 001's 34-test fake suite still green (FR-010 unchanged logic).
- `T:` post-redeploy: `ss`/`curl` shows 8643 AND 8644 listening; an offer to
  8644 returns an answer (SC-001/SC-002/SC-006).
- `T:` `rollback.sh` still restores pre-redeploy state exactly (SC-004).
