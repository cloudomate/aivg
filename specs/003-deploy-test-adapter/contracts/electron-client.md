# Contract: Electron Test Client (design satellite #3)

Minimal desktop client whose only job is to prove the deployed adapter with a
real human spoken exchange. Implements the design's satellite-#3 contract; adds
nothing to the satellite runtime guarantees (constitution I/II/III).

## Connections (two, per the generic contract — constitution III)

- **Control**: always-on WebSocket to `WS /satellite/ws` (register, heartbeat),
  via the SSH-forwarded management port (8643).
- **Voice**: one `RTCPeerConnection` per call. Client is the **offerer**:
  `getUserMedia` → add audio track → **full ICE gather** → `POST /webrtc/offer`
  to the forwarded WebRTC port (8644) → apply answer. `/webrtc/candidate` not
  used on the forwarded/LAN path.

## Capture / playback

| Concern | Required behaviour |
|---------|--------------------|
| Mic | `getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true,channelCount:1,sampleRate:48000}})` |
| Echo | Chromium AEC only (`browser_aec3`) — NO server-side ducking, NO app-side echo code |
| Playback | hidden `<audio autoplay>` bound to the remote stream; needs a user gesture (Connect) |
| Endpointing | push-to-talk button for v1 (press-hold or toggle); gateway still owns authoritative end-of-utterance |
| Barge-in | mic stays open; speaking during playback reaches the gateway and cancels the reply (SC-003) |
| Wake word | NONE in v1 (design defers to v2) |

## Behaviour contract

- The client performs **no STT/TTS/agent/endpointing** (constitution I) — it
  only moves Opus audio and shows minimal state.
- Mic-permission denied → surface the OS settings path; the test cannot be
  marked passed without real audio input.
- Connection lost → attempt reconnect of the control WS; a dropped call needs a
  fresh offer (no gateway restart).
- Minimal UI: Connect, push-to-talk control, current state
  (idle/listening/thinking/speaking), last transcript/reply text (from the
  optional call-scoped UI events), and an on-screen latency readout
  (end-of-speech → first audio) for SC-002.

## Conformance checks (→ tasks)

- `T:` registers over the control WS and appears in `/satellite/list`.
- `T:` offer is full-gathered (no trickle needed on the forwarded path);
  negotiated codec Opus 48 kHz mono, no SDP munging.
- `T:` a spoken phrase yields an audible agent reply; measured
  end-of-speech→reply shown and ≤1.5 s nominal (SC-002).
- `T:` talking over playback stops it ≤300 ms and starts a new turn (SC-003).
- `T:` agent audio does not loop back as new input (AEC working).
- `T:` no STT/TTS/agent library is bundled in the client (constitution I).
