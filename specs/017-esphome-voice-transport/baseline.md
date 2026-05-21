# Pre-Implementation Baseline (feature 017)

**Date**: 2026-05-21
**Branch base**: `015-agentplatform-runtime-closure` HEAD = `5f0025c` (017 branched from here)

## Test suite baseline (T002)

Single run pre-implementation:

```
290 passed, 1 xpassed, 1 warning in 6.09s
```

Same numbers across 3+ runs in feature 015 closeout. This is the floor: after 017 lands the suite must show **290 + new tests passed**.

## Contract version baseline (T003)

```bash
/Users/ys/.hermes/hermes-agent/venv/bin/aivg --contract-version
```

**Output**:

```json
{"ok":true,"data":{"contract_version":"1.0.0"},"error":null,"v":1}
```

Target post-017: `{"contract_version":"1.1.0","transports":["webrtc","esphome_api"]}` (or `["webrtc"]` when ESPHome transport disabled).

## aioesphomeapi installed (T001)

```
Name: aioesphomeapi
Version: 27.0.3
```

Installed into `/Users/ys/.hermes/hermes-agent/venv/`. Proto schemas + framing helpers verified importable:

- `aioesphomeapi.api_pb2.HelloRequest` ✓
- `aioesphomeapi.api_pb2.VoiceAssistantAudio` (fields: `data`, `end`) ✓
- `aioesphomeapi.api_pb2.VoiceAssistantRequest` (fields: `start`, `conversation_id`, `flags`, `audio_settings`, `wake_word_phrase`) ✓
- `aioesphomeapi.api_pb2.VoiceAssistantEventResponse` (fields: `event_type`, `data`) ✓
- `aioesphomeapi.core.MESSAGE_NUMBER_TO_PROTO` — tuple indexed by opcode ✓
- `aioesphomeapi._frame_helper.plain_text.varuint_to_bytes` — reusable for outbound encoding (private but stable; we'll re-implement varint decode locally to avoid private-API import)

**Opcode table for the messages this feature handles**:

|  Opcode | Message |
|---:|---|
| 0 | HelloRequest |
| 1 | HelloResponse |
| 2 | ConnectRequest |
| 3 | ConnectResponse |
| 4 | DisconnectRequest |
| 5 | DisconnectResponse |
| 6 | PingRequest |
| 7 | PingResponse |
| 8 | DeviceInfoRequest |
| 9 | DeviceInfoResponse |
| 10 | ListEntitiesRequest |
| 18 | ListEntitiesDoneResponse |
| 88 | SubscribeVoiceAssistantRequest |
| 89 | VoiceAssistantRequest |
| 90 | VoiceAssistantResponse |
| 91 | VoiceAssistantEventResponse |
| 105 | VoiceAssistantAudio |
| 120 | VoiceAssistantConfigurationRequest |
| 121 | VoiceAssistantConfigurationResponse |

## Wire format (confirmed by reading `aioesphomeapi._frame_helper.plain_text.APIPlaintextFrameHelper`)

Outbound, per message:

```
\x00              (1-byte preamble; always 0 for plaintext)
varuint(len)      (1-5 bytes, length of payload in bytes)
varuint(opcode)   (1-5 bytes, message-type opcode from table above)
payload           (len bytes, protobuf-serialized message)
```

Inbound: same three varints, then read `len` bytes.

## Post-implementation receipts

- **T028 full-suite x3**: **329 passed, 1 xpassed, 0 failed** across 3 consecutive runs ✓ (was 290 pre-017; +39 new tests)
- **T029 wire-surface live**: in-process `FakeEsphomeClient` completed Hello + Connect handshake against the live gateway's port 6053 ✓
- **T030 contract version live**: `aivg --contract-version` → `{"contract_version":"1.1.0","transports":["webrtc","esphome_api"]}` (was `1.0.0`) ✓
- **T036 multi-device concurrency**: 4 concurrent ESPHome clients each complete one turn against the echo platform; all within 1.5× single-device budget ✓
- **T038 disconnect cleanup**: 30 mid-turn drops → task count returns to 0 within 2 s ✓
- **T046 live ESPHome device smoke**: gateway dialer started + the `respeaker-xvf-1` keystore entry generated; flashing recipe at [flash-respeaker-xvf3800.md](./flash-respeaker-xvf3800.md). Hardware-flash step deferred to the user (see Recipe for the YAML patch + `aivg` config block). Once the device is on the LAN and reachable, the dialer will pick it up automatically (no further gateway action required).
- **T050 final commit-time checks**:
  - `rg '# AgentPlatform-coupling-TODO' src/aivg_core/` → 0 ✓
  - `grep transports/esphome src/aivg_core/platforms/` → 0 ✓
  - `git diff 015-agentplatform-runtime-closure...HEAD -- src/aivg_core/platforms/` → empty ✓
  - `git diff 015-agentplatform-runtime-closure...HEAD -- src/aivg_core/webrtc/session.py` → empty ✓

## Live-gateway smoke (T046 prep)

After running `pip install -e .` into the Hermes venv and restarting
the gateway with `transports.esphome_api.enabled: true`:

- Gateway pid 52699 listening on **8643** (mgmt), **8644** (WebRTC), **6053** (ESPHome) ✓
- `aivg list` table shows the new `transport` column ✓
- A test ESPHome client (in-process) successfully registered as
  `smoke-test-device` with `transport: esphome_api` ✓

Direction-of-connection note: feature 017 ships **both** modes —
**server** (port 6053 listener, for OHF-Voice-style satellites that
dial AIVG) AND **client** (the dialer, for real ESPHome firmware that
listens on its own port 6053). The two modes are independent and can
both run simultaneously. Real ESP32 devices use client mode (the
dialer); see [flash-respeaker-xvf3800.md § Step 5](./flash-respeaker-xvf3800.md#step-5--configure-aivg-to-dial-the-device).
