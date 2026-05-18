# Implementation Plan: Deploy & Live-Test the Voice Adapter on the Hermes Gateway

**Branch**: `003-deploy-test-adapter` | **Date**: 2026-05-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-deploy-test-adapter/spec.md`

## Summary

Deploy feature 001's adapter onto the running Hermes gateway as a **platform
plugin** (mirroring `plugins/platforms/irc/`), add a backed-up `satellite:`
config block, restart the gateway, then drive one real human spoken
conversation from a minimal **Electron/JS satellite-#3 client** (push-to-talk
v1, Chromium AEC). Every host-mutating step is backed up + confirmed, with a
one-command rollback. This is the concrete closure of feature 001's open T045.

**Phase 0 verified on the live host (read-only):** `aiortc`, `aiohttp`, `av`
are all installed in the Hermes venv — the production transport can actually
run there (001's "needs aiortc" constraint is lifted). Plugin platforms load
from `plugins/platforms/<name>/` via a `plugin.yaml` (`kind: platform`) + an
`__init__.py` that self-registers a `PlatformEntry`; the gateway discovers them
sequentially at startup. `~/.hermes/config.yaml` exists and Hermes already
keeps timestamped `config.yaml.bak.*` files.

## Technical Context

**Language/Version**: Python 3.11+ adapter (host venv: 3.12) + a small
Electron/JS client (Node LTS). Deploy/rollback = bash + `ssh hermes`.
**Primary Dependencies**: host already has `aiortc`/`aiohttp`/`av`; Electron +
the browser WebRTC stack for the client; `gh`/`git`/`rsync`/`ssh` for deploy.
**Storage**: No DB. Host `~/.hermes/config.yaml` (`satellite:` block, backed
up); deployed plugin tree under `…/hermes-agent/plugins/platforms/satellite_webrtc/`;
test results recorded under this repo's `specs/003-*/` or a results file.
**Testing**: Manual human-driven spoken exchange (the actual implementation
test) + automated pre/post regression check that existing gateway platforms are
unaffected + a rollback-restores-exactly check.
**Target Platform**: `ssh hermes` host (hermes-agent v0.13.0, Linux x86_64);
Electron client on the developer's machine reaching the host via SSH
port-forward of the management/WebRTC ports.
**Project Type**: Deployment + a thin desktop test client; no new adapter code
(reuses 001's package; only a plugin shim + `plugin.yaml`).
**Performance Goals**: SC-002 reply ≤1.5 s after end-of-speech; SC-003 barge-in
≤300 ms; SC-006 rollback ≤5 min.
**Constraints**: production gateway → FR-003 backup-first, FR-004 confirm every
host mutation, FR-005 one-step rollback, FR-006 no silent partial deploy,
FR-002/SC-005 zero regression; FR-014 keep constitution runtime guarantees.
**Scale/Scope**: one host, one Electron client, one concurrent conversation
(multi-client load is feature 001's fake-suite scope, out of scope here).

**Resolved (no NEEDS CLARIFICATION):** deploy mechanism, dependency
availability, config path, and registration path verified live in Phase 0;
client type / networking / PTT-v1 fixed by spec Assumptions.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Gate | Status |
|---|-----------|------|--------|
| I | Thin Satellite, Gateway-Owned Intelligence | Deployed adapter still embeds no STT/TTS/agent/endpointing; Electron client only captures/plays audio | ✅ PASS |
| II | Generic Four-Plane Contract | Electron client is design satellite #3 implementing the same contract; no gateway device-branching | ✅ PASS |
| III | Separate Control and Voice Connections | Deployed adapter keeps always-on control + per-call WebRTC; Electron client uses both | ✅ PASS |
| IV | Reuse Hermes, Don't Rebuild | Deployed as a Hermes platform plugin via the verified `PlatformRegistry`; reuses config.yaml/providers/agent — nothing rebuilt | ✅ PASS |
| V | Research-Backed, Verify Before Relying | This feature *is* the live verification; deploy mechanism verified read-only on the host before any mutation; backup+confirm+rollback gate every change | ✅ PASS (fulfils V) |

**Result: PASS, no violations.** Production-safety requirements (backup/confirm/
rollback) exceed the constitution minimum and match the project's
outward-action posture. Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/003-deploy-test-adapter/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/
│   ├── deployment-procedure.md   # backup→confirm→deploy→verify→rollback contract
│   └── electron-client.md        # satellite-#3 client behaviour contract
└── tasks.md                      # /speckit-tasks output (not here)
```

### Repository assets (created by this feature)

```text
deploy/
├── deploy-to-hermes.sh     # backup → confirm → vendor plugin → add satellite: block → restart → verify
├── rollback.sh             # restore config.yaml backup → remove plugin → restart → verify (FR-005)
└── plugin/
    ├── plugin.yaml         # kind: platform, name/label/version (mirrors plugins/platforms/irc/)
    └── __init__.py         # imports hermes_satellite_adapter + platform_registry.register(PlatformEntry)

clients/electron-test/      # minimal Electron satellite #3 (FR-007/008/010)
├── package.json  main.js   # tray/window, SSH-forwarded host config
└── renderer.{html,js}      # getUserMedia(AEC on) + RTCPeerConnection (offerer,
                            #   full ICE gather → POST /webrtc/offer) + control WS
                            #   + hidden <audio> playback + push-to-talk button
```

### Host layout after deploy (on `ssh hermes`)

```text
~/.hermes/hermes-agent/plugins/platforms/satellite_webrtc/   # vendored 001 package + shim
~/.hermes/config.yaml            # + satellite: block  (backup: config.yaml.bak.<ts> first)
```

**Structure Decision**: No new adapter code — feature 001's
`hermes_satellite_adapter` package is vendored onto the host inside a
platform-plugin shim that registers the verified `PlatformEntry` (001 T044).
The only new code is (1) deploy/rollback scripts and the plugin shim, and (2) a
deliberately minimal Electron client implementing the design's satellite-#3
contract. Irreversible host steps are isolated in `deploy/` behind
backup+confirm; `rollback.sh` is the inverse and is tested (FR-005/SC-006).

## Complexity Tracking

> Not applicable — Constitution Check passed with no violations.
