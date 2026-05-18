# Phase 1 Data Model: Serve the WebRTC Signaling Site & Redeploy

No persistent data. The "model" is the adapter's two-plane lifecycle state.

## Entity: Adapter Network Planes

| Field | Rule |
|-------|------|
| `management_site` | aiohttp site on `management_port` (control plane) — already worked |
| `signaling_site` | aiohttp site on `webrtc_port` (voice plane) — **added by this feature** |
| `runners` | `self._sites` MUST contain BOTH runners after a successful start (FR-004 teardown depends on it) |
| `ready` | true ⇔ BOTH sites bound; control-up/signaling-down ⇒ NOT ready (FR-005/SC-005) |

**Invariant**: there is no valid state where the adapter is "ready/connected"
with only one site bound. Signaling bind failure ⇒ management site torn down +
start raises.

## State transitions (adapter lifecycle)

```
stopped --start--> bind mgmt --ok--> bind signaling --ok--> READY (both planes)
                                  \--fail--> tear down mgmt --> raise (NOT ready)  [FR-005]
bind mgmt --fail--> raise (NOT ready)
READY --stop--> cleanup all runners --> stopped (no orphan listeners)  [FR-004]
```

## Entity: Redeployment (reused from feature 003)

| Field | Note |
|-------|------|
| backup_ref | `config.yaml.bak.f003.*` taken before redeploy (existing script) |
| verify | extended: adapter registered + constitution-I + SC-005 + **both ports listening** (new) |
| rollback | `deploy/rollback.sh` — unchanged, tested undo (SC-004) |

State transitions reuse feature 003's deployment lifecycle
(`preflight → confirm → backup → apply → verify|rollback`); only the `verify`
predicate gains the both-ports check.

## Non-entities

`Session`, `ConversationTurn`, the bridge, STT/TTS/agent — all unchanged
(FR-010). Signaling endpoint request/response shapes are defined by feature
001's `contracts/webrtc-signaling.md` and reused verbatim.
