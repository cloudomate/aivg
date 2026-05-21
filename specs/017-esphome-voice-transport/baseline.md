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

## Post-implementation receipts (filled in by tasks)

- T028 full-suite x3: _TBD_
- T029 electron-test live smoke: _TBD_
- T030 contract version post-implementation: _TBD_
- T036 multi-device concurrency: _TBD_
- T038 disconnect cleanup: _TBD_
- T046 live ESPHome device smoke: _TBD_
- T050 final commit-time checks: _TBD_
