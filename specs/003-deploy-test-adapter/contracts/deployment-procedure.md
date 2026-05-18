# Contract: Deployment & Rollback Procedure

Production gateway. Every host mutation is backed up + explicitly confirmed;
rollback is mandatory and tested (FR-003/004/005/006, SC-006/007).

## `deploy/deploy-to-hermes.sh` — ordered, gated steps

| # | Step | Mutating? | Gate |
|---|------|-----------|------|
| 1 | Preflight: `ssh hermes` reachable; gateway running; `aiortc/aiohttp/av` import in venv; capture `pre_existing_platforms` | no | — |
| 2 | Show planned changes; **WAIT for explicit operator confirmation** | no | FR-004 |
| 3 | Backup `~/.hermes/config.yaml` → `config.yaml.bak.<ISO>`; record ref | yes (additive) | confirmed |
| 4 | rsync vendored 001 package + shim → `…/plugins/platforms/satellite_webrtc/` | yes | confirmed |
| 5 | Add `satellite:` block to `~/.hermes/config.yaml` (idempotent; no-op if present) | yes | confirmed |
| 6 | Restart the gateway (per host's documented surface) | yes | confirmed |
| 7 | Post-verify: adapter registered + endpoints reachable + a pre-existing platform still works | no | — |

Failure handling: a failure at/after step 4 MUST either auto-restore the
backup+remove the plugin dir, or stop and print **`ROLLBACK REQUIRED`** with
the backup ref — never leave a silent partial deploy (FR-006).

## `deploy/rollback.sh` — the exact inverse

1. Restore `~/.hermes/config.yaml` from the recorded backup ref (byte-for-byte).
2. Remove `…/plugins/platforms/satellite_webrtc/`.
3. Restart the gateway.
4. Verify `pre_existing_platforms` behaviour == captured pre-state (SC-005);
   exit non-zero if not identical.

Target: completes in <5 min and reproduces pre-deployment state exactly
(SC-006).

## Conformance checks (→ tasks)

- `T:` preflight aborts with no mutation if the gateway is unreachable.
- `T:` no step ≥3 runs without a recorded confirmation (FR-004/SC-007).
- `T:` `config.yaml` backup exists and is byte-identical to pre-state before
  any edit (FR-003).
- `T:` after deploy, the adapter is registered AND a pre-existing platform is
  unaffected (FR-001/FR-002/SC-005).
- `T:` `rollback.sh` restores `config.yaml` byte-for-byte and removes the
  plugin dir; post-state == pre-state (SC-006).
- `T:` an injected mid-deploy failure yields restored-or-flagged, never silent
  partial (FR-006).
