# Quickstart: Deploy & Live-Test on the Hermes Gateway

> Targets a **production** gateway. Steps 2–5 mutate the host and each pause
> for explicit confirmation; `rollback.sh` is the tested undo (SC-006).

## 0. Preflight (read-only, no mutation)

```bash
deploy/deploy-to-hermes.sh --preflight
# checks: ssh hermes reachable; gateway running; aiortc/aiohttp/av in venv;
# captures the pre-existing platform list for the regression check
```

## 1. Deploy (gated)

```bash
deploy/deploy-to-hermes.sh
# prints the exact planned host changes, then WAITS for "yes":
#   backup ~/.hermes/config.yaml → config.yaml.bak.<ISO>
#   rsync vendored adapter → …/plugins/platforms/satellite_webrtc/
#   add `satellite:` block to ~/.hermes/config.yaml
#   restart gateway
#   post-verify: adapter registered + a pre-existing platform still works
```

If anything fails mid-way it restores the backup + removes the plugin dir, or
stops with `ROLLBACK REQUIRED <backup-ref>` — never a silent partial deploy.

## 2. Forward the adapter ports to your machine

```bash
ssh -N -L 8643:localhost:8643 -L 8644:localhost:8644 hermes
```

## 3. Run the Electron test client

```bash
cd clients/electron-test && npm install && npm start
```

Click **Connect** (grants mic + satisfies autoplay), then **push-to-talk**:
speak a request, release, and listen for the Hermes agent's spoken reply. The
window shows state and the end-of-speech→reply latency.

## 4. Validate (SC-001..SC-005, SC-008)

- One full spoken exchange completes with an audible agent reply (SC-001).
- Latency readout ≤ 1.5 s nominal (SC-002).
- Talk over the reply → it stops ≤300 ms, new turn starts (SC-003).
- Agent audio doesn't echo back (AEC working).
- Operator: `curl -s localhost:8643/satellite/list | jq .` shows the client +
  live state; per-session logs retrievable; record pass/fail + latency (SC-008).
- Re-exercise a pre-existing gateway platform → unchanged (SC-005).

## 5. Roll back (always, when done or on failure)

```bash
deploy/rollback.sh
# restore config.yaml backup byte-for-byte → remove plugin dir → restart →
# verify pre-existing platforms == captured pre-state (exits non-zero if not)
```

## Notes

- All host dependencies (`aiortc/aiohttp/av`) are already present — no install
  on the host (verified Phase 0).
- Feature 002's vendored `hermes-agent` skill MAY be used to perform/validate
  the gateway config steps; host-mutating skill steps are confirmation-gated.
- ⚠️ `ssh hermes` host key changed earlier this project and was confirmed
  legitimate by the user — fine to use.
