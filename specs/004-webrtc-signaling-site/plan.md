# Implementation Plan: Serve the WebRTC Signaling Site & Redeploy

**Branch**: `004-webrtc-signaling-site` | **Date**: 2026-05-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/004-webrtc-signaling-site/spec.md`

## Summary

Close the defect feature 003's live deploy surfaced: `adapter.start()` starts
only the management site — the WebRTC signaling site (`webrtc_port`/8644) is a
code comment, so no voice session can be negotiated. Fix = add a
`build_signaling_app()` to `signaling.py` (mirroring the existing
`build_management_app()`) and have `adapter.start()` bring up **both** sites,
with a readiness gate so "control-up / signaling-down" is reported as
not-ready (FR-005/SC-005). Then **gated-redeploy** via feature 003's existing
`deploy/deploy-to-hermes.sh` (the T027 path), extending its post-verify to
assert both ports listen. No conversation-logic or contract changes.

## Technical Context

**Language/Version**: Python 3.11+ (host venv 3.12). Change is ~2 files +
deploy post-verify; no new deps (`aiohttp`/`aiortc`/`av` already on host,
verified feature 003).
**Primary Dependencies**: `aiohttp` (already used by `build_management_app`);
feature 003 `deploy/deploy-to-hermes.sh` / `rollback.sh` reused unchanged for
the redeploy path.
**Storage**: none new.
**Testing**: fake-transport unit suite (feature 001, 34 tests — must stay
green); a unit check that `build_signaling_app` exposes the `/webrtc/*` routes
and the start/stop lifecycle tracks both runners; binding/both-ports proven on
the host post-deploy (SC-001).
**Target Platform**: `ssh hermes` host (hermes-agent v0.13.0); adapter runs in
the gateway process.
**Project Type**: Single Python package change + redeploy via existing scripts.
**Performance Goals**: n/a (lifecycle fix); SC-004 rollback <5 min reused.
**Constraints**: FR-003 two planes stay separate ports; FR-005 not-ready if
signaling down; FR-006 reuse the gated reversible deploy; FR-009/010 keep
constitution runtime guarantees + conversation logic/contract unchanged.
**Scale/Scope**: deliberately tiny — `signaling.py` (+builder),
`adapter.py` (start both + ready gate), `deploy/deploy-to-hermes.sh`
(post-verify both ports). Nothing else.

**Resolved (no NEEDS CLARIFICATION):** change site read directly; signaling
endpoint behaviour already pinned by feature 001's webrtc-signaling contract;
deploy mechanism verified live in feature 003.

## Constitution Check

| # | Principle | Gate | Status |
|---|-----------|------|--------|
| I | Thin Satellite, Gateway-Owned Intelligence | Signaling site is pure transport; no STT/TTS/agent added | ✅ PASS |
| II | Generic Four-Plane Contract | Voice-plane endpoint set unchanged (feature 001 contract) | ✅ PASS |
| III | Separate Control and Voice Connections | This fix **enforces** III: two separate aiohttp sites/ports; readiness gate forbids the half-up state | ✅ PASS (reinforces) |
| IV | Reuse Hermes, Don't Rebuild | Reuses `build_management_app` pattern + feature 003 deploy/rollback; nothing rebuilt | ✅ PASS |
| V | Research-Backed, Verify Before Relying | Change site inspected directly; post-deploy verifies BOTH ports listen before declaring done | ✅ PASS (reinforces) |

**Result: PASS, no violations.** Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/004-webrtc-signaling-site/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/signaling-site-lifecycle.md
└── tasks.md   # /speckit-tasks (not here)
```

### Code changes (this feature)

```text
src/hermes_satellite_adapter/signaling.py
  + build_signaling_app(service)        # lazy aiohttp; routes:
                                        #   POST /webrtc/offer   -> handle_offer
                                        #   POST /webrtc/candidate -> 204 (fallback)
                                        #   GET  /webrtc/status/{device_id} -> status

src/hermes_satellite_adapter/adapter.py
  ~ start(): build+start BOTH sites (mgmt :management_port,
             signaling :webrtc_port); track both runners; if the signaling
             site fails to bind -> tear down mgmt + raise (FR-005) so the
             gateway never reports the adapter ready/connected half-up.
  ~ stop():  already cleans every runner — ensure both are appended.

deploy/deploy-to-hermes.sh
  ~ postverify(): additionally assert BOTH :management_port and :webrtc_port
                  are listening on the host (SC-001) — extends, not replaces,
                  the existing constitution-I + SC-005 checks.

tests/unit/test_adapter_sites.py   # new: build_signaling_app route set;
                                   # start() registers two runners; signaling
                                   # bind-failure path raises & tears down mgmt
```

**Structure Decision**: Smallest viable change at the exact defect site.
`build_signaling_app` mirrors the proven `build_management_app` (constitution
IV — reuse the pattern). The readiness gate turns the 003 lesson into enforced
behaviour (FR-005). Redeploy is **feature 003's existing gated path** invoked
again (T027) — only its post-verify grows a both-ports assertion; no new deploy
mechanism. Feature 001's conversation logic, `session.py`, the bridge, and the
fake-transport test suite are untouched.

## Complexity Tracking

> Not applicable — Constitution Check passed with no violations.
