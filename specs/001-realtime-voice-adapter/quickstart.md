# Quickstart: Realtime Voice Platform Adapter

Bring up the lowest-risk end-to-end loop (build-order #1: gateway adapter +
browser-style client over loopback aiortc) and prove the constitution-I
boundary with a fake Hermes bridge — no real Hermes build or hardware needed.

## Prerequisites

- Python 3.11+, `ffmpeg` on PATH
- `pip install aiortc aiohttp av pytest pytest-asyncio`
- This repo checked out on branch `001-realtime-voice-adapter`

## 1. Configure (reuses the existing Hermes config file shape)

Add to `~/.hermes/config.yaml` (existing `voice:`/`stt:`/`tts:` blocks
unchanged — satellites inherit them):

```yaml
satellite:
  enabled: true
  management_port: 8643
  webrtc_port: 8644
  heartbeat_interval: 30
  mdns_advertise: true
  default_config:
    wake_word: "Hey Jarvis"
    routing_mode: "preferred"
    log_level: "INFO"
```

No new secret store — `~/.hermes/.env` is reused as-is.

## 2. Run the adapter (standalone dev harness)

For local development the package can be started with the **fake Hermes
bridge** so STT/agent/TTS are deterministic:

```bash
python -m hermes_satellite_adapter --dev-fake-bridge
# management plane → http://localhost:8643
# webrtc signaling → http://localhost:8644
```

In production it is not started this way — it is loaded as a platform adapter
by the running Hermes gateway (see VG-4); the `--dev-fake-bridge` harness
exists only for the test loop.

## 3. Drive the P1 loop (loopback)

```bash
pytest tests/integration/test_p1_conversation.py -q
```

Expected: a loopback aiortc client registers, opens a WebRTC session
(full-gather offer → answer), streams a scripted utterance, and receives a
spoken reply from `FakeHermesBridge` — asserting reply audio begins within the
SC-001 budget.

## 4. Verify the key behaviors

```bash
pytest tests/ -q
```

Covers:

- **P1** speech→agent→speech loop (SC-001 latency)
- **Barge-in**: speaking is cancelled ≤300 ms on inbound speech (SC-003)
- **Control plane**: `WS /satellite/ws` stays up with no active call (SC-006)
- **Reconnect**: ICE drop → re-offer works without gateway restart (SC-007)
- **Provider fallback / all-fail**: graceful perceptible failure (FR-015)
- **Concurrency**: 10 simultaneous sessions within 1.5× latency (SC-005)
- **Constitution-I lint**: no `whisper`/`piper`/engine import outside
  `hermes_bridge`

## 5. Manual smoke (optional, browser-style)

```bash
curl -s localhost:8643/satellite/list | jq .
# expect the loopback test client listed as "online" with its session state
```

## 6. Before relying on a real Hermes build

Close the research verification gates **VG-1..VG-4** (provider interface
names, endpointing entrypoint, agent entrypoint, adapter registration/CLI).
Only `hermes_bridge.py` + the registration shim change; the rest of the
package and all tests stay as-is.
