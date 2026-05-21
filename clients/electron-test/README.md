# AIVG Satellite — Electron Test Client

Minimal satellite client consuming `@aivg/sat-sdk` to live-test the
AIVG voice adapter (running the Hermes platform plugin). Does no
STT/TTS/agent (constitution I) — only mic capture, WebRTC transport,
and playback (Chromium AEC3 handles local echo).

Originally bootstrapped in feature 003; refactored onto
`@aivg/sat-sdk` in feature 014 as the SDK's living integration test.

## Use

1. **Install AIVG into your Hermes venv** (skip if already done):
   ```bash
   uv pip install --python ~/.hermes/hermes-agent/venv/bin/python aivg
   ```
   Then add `aivg-satellite` to `plugins.enabled:` in
   `~/.hermes/config.yaml` and restart Hermes. (Or run `aivg setup`.)

2. **Local-only**: gateway ports are bound on `localhost`. If you're
   testing against a remote Hermes host, forward the ports:
   ```bash
   ssh -N -L 8643:localhost:8643 -L 8644:localhost:8644 <hermes-host>
   ```

3. **Run the client**:
   ```bash
   cd clients/electron-test && npm install && npm start
   ```

4. Click **Connect** (grants mic + satisfies autoplay), then
   press-and-hold **Push to talk**, speak, release, and listen for
   the agent's reply. The window shows state and the
   end-of-speech→reply latency (SC-002 ≤ 1500 ms).

5. Barge-in: hold PTT again while it's speaking → playback stops,
   new turn.

## Notes

- Two connections: always-on control WS + per-call RTCPeerConnection
  (constitution III). Client is the offerer; offer is
  full-ICE-gathered before POST (design §2.2).
- Wake word is intentionally absent in v1 (design defers to v2).
- The feature-003 deploy scripts (`deploy/deploy-to-hermes.sh`,
  `deploy/rollback.sh`, `deploy/parity-check.sh`) were removed in
  feature 018 — superseded by `aivg setup` (feature 013).
