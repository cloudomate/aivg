# Contract: WebRTC Signaling Plane (`:8644`)

Per-session voice negotiation. The **client/satellite is the offerer**; the
**adapter is the answerer** (design §2.2, all device types). Audio-only, one
PC per session, Opus 48 kHz mono. Source of truth: design §2.2.

## Endpoints

```
POST /webrtc/offer
  req : { sdp, type:"offer", device_id }
  res : 200 { sdp, type:"answer" }
  note: client does FULL ICE GATHER, then sends the complete SDP.
        Adapter sets remote desc, creates answer, returns it. A VoiceSession
        is created and bound to the ConnectedClient (device_id).

POST /webrtc/candidate            (FALLBACK ONLY — LAN clients skip this)
  req : { candidate, sdpMid, label, device_id }
  res : 204

GET  /webrtc/status/{device_id}
  res : 200 { webrtc_state, session_id, bitrate_tx, bitrate_rx, state }
        404 if no session
```

## Audio behavior

- Inbound track: Opus → PCM frames → `hermes_bridge.stt_transcribe` /
  `detect_endpoint`. Device VAD only gates the upstream stream; Hermes owns
  turn-end (constitution I).
- Outbound track: `hermes_bridge.tts_synthesize` audio → Opus encode (explicit
  ~24–32 kbps) → client.
- Optional single SCTP datachannel: call-scoped UI only (partial transcript,
  listening/speaking, barge-in). No durable control here (constitution III).

## Session lifecycle

- Offer → answer creates `VoiceSession(state=listening)`.
- ICE/connection drop → tear down Session, free the turn, keep
  ConnectedClient; expect a fresh offer (FR-014 / design Appendix E).
- Gateway restart → active sessions end; clients re-register.

## Conformance tests (contract/)

- Full-gather offer yields a valid answer with one audio m-line, no video.
- `/candidate` works as fallback but is unnecessary on loopback/LAN.
- `/status` reports `webrtc_state` transitions and bitrate telemetry.
- ICE drop tears the Session down and a re-offer establishes a new one
  without gateway restart.
- Negotiated codec is Opus 48 kHz mono; no SDP munging.
