# Quickstart: Serve the WebRTC Signaling Site & Redeploy

## 1. Apply the fix (local code)

- `src/hermes_satellite_adapter/signaling.py`: add `build_signaling_app(service)`
  (lazy aiohttp; routes `/webrtc/offer|candidate|status` → `SignalingService`).
- `src/hermes_satellite_adapter/adapter.py` `start()`: build+start the signaling
  site on `cfg.webrtc_port` after the management site; record both runners; on
  signaling bind-failure tear down the management site and raise (FR-005).

## 2. Verify locally (no host, no aiohttp needed)

```bash
.venv/bin/python -m pytest -q          # feature 001 suite stays green (FR-010)
.venv/bin/python -m pytest -q tests/unit/test_adapter_sites.py
# asserts: build_signaling_app routes; start registers 2 runners;
#          signaling-bind-failure raises + tears down mgmt (FR-004/FR-005)
```

## 3. Gated redeploy (production — reuses feature 003 path, T027)

```bash
deploy/deploy-to-hermes.sh --preflight        # read-only
deploy/deploy-to-hermes.sh                     # gated; backs up, rsyncs the
                                               # fixed package, restarts,
                                               # post-verify now also asserts
                                               # 8643 AND 8644 are listening
```

A failed both-ports check fails the deploy with a `ROLLBACK REQUIRED` hint.

## 4. Confirm the gap is closed

```bash
ssh hermes 'ss -ltn | grep -E ":(8643|8644)"'   # BOTH must be LISTEN (SC-001)
ssh hermes 'curl -s -m5 localhost:8643/satellite/list'   # control plane ok
# then forward + Electron client (feature 003 T018-T020):
ssh -N -L 8643:localhost:8643 -L 8644:localhost:8644 hermes
cd clients/electron-test && npm start   # Connect → push-to-talk → hear reply
```

## 5. Roll back when done / on failure

```bash
deploy/rollback.sh        # unchanged feature-003 tested undo (SC-004)
```

## Notes

- Only `signaling.py` (+builder) and `adapter.py` (`start`) change in the
  package; deploy script gains a both-ports post-check. Conversation logic,
  `session.py`, bridge, satellite contract: untouched (FR-009/010).
- The live spoken exchange still needs a human at a mic — this feature only
  removes the signaling blocker so feature 003 T018–T020 can proceed.
