# AIVG Satellite — Electron Test Client (feature 003)

Minimal satellite-#3 client to live-test the **deployed** AIVG voice
adapter (running the Hermes platform plugin). Does no STT/TTS/agent
(constitution I) — only mic capture, WebRTC transport, and playback
(Chromium AEC3 handles local echo).

## Use

1. Deploy the adapter (from repo root): `deploy/deploy-to-hermes.sh`
   (gated; confirms each production-host change).
2. Forward the adapter ports:
   `ssh -N -L 8643:localhost:8643 -L 8644:localhost:8644 hermes`
3. `cd clients/electron-test && npm install && npm start`
4. Click **Connect** (grants mic + satisfies autoplay), then press-and-hold
   **Push to talk**, speak, release, and listen for the agent's reply. The
   window shows state and the end-of-speech→reply latency (SC-002 ≤ 1500 ms).
5. Barge-in: hold PTT again while it's speaking → playback stops, new turn.
6. When done (or on any failure): `deploy/rollback.sh`.

## Notes

- Two connections: always-on control WS + per-call RTCPeerConnection
  (constitution III). Client is the offerer; offer is full-ICE-gathered
  before POST (design §2.2).
- Parity (SC-004): run `deploy/parity-check.sh "<phrase you spoke>"` and
  compare to what you heard/saw.
- Wake word is intentionally absent in v1 (design defers to v2).
