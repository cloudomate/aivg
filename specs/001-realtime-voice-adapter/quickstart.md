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

## 6. Wiring the real Hermes (v0.13.0) — gates resolved

VG-1..VG-4 are resolved (see research.md). On the Hermes host
(`/home/ubuntu/.hermes/hermes-agent/`, venv at `…/venv`) implement
`HermesV013Bridge` against the verified entrypoints:

- STT: `from tools.transcription_tools import transcribe_audio` — write PCM to
  a temp WAV, call `transcribe_audio(path)`, take the extracted text.
- TTS: `from tools.tts_tool import text_to_speech_tool` — parse the returned
  JSON, read `file_path`, decode → PCM/Opus.
- Endpointing: reuse `tools.voice_mode.SILENCE_RMS_THRESHOLD` /
  `SILENCE_DURATION_SECONDS` (the RMS/duration rule) over decoded WebRTC PCM.
- Register: `PlatformRegistry.register(PlatformEntry(name="satellite_webrtc",
  source="plugin", adapter_factory=…, check_fn=…))`; manage with
  `hermes gateway` / configure with `hermes gateway setup`.

Only `hermes_bridge.py` (new `HermesV013Bridge`) and `adapter.py` change; the
package core and the entire fake-driven test suite stay as-is. Remaining
narrowed item: confirm the exact adapter connect/receive/send-reply methods by
reading one full built-in adapter (`gateway/platforms/discord.py`) on the host.

> Note: the `ssh hermes` host key changed during this work — verify the
> fingerprint is expected before trusting/connecting for the live wiring.
