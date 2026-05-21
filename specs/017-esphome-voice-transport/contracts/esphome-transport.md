# Contract — ESPHome Voice Assistant transport

**Feature**: 017-esphome-voice-transport · **Phase**: 1 · **Date**: 2026-05-21

This is the binding contract the ESPHome transport satisfies, so any
upstream ESPHome firmware (Home Assistant Voice Preview Edition,
M5Stack Atom Echo, custom builds from ESPHome's voice-satellite YAML)
talks to AIVG without modification, AND so the existing WebRTC clients
remain byte-identical.

Type signatures and message-shape definitions are normative; see
[../data-model.md](../data-model.md) for the canonical Python source.

---

## 1. Listener contract

The gateway exposes a TCP listener bound to a configurable host:port
(default `0.0.0.0:6053`) when `transports.esphome_api.enabled = true`
in the satellite config. The listener:

1. Accepts incoming TCP connections without TLS (v1 plaintext only —
   OOS-001 defers encryption to v1.1).
2. Spawns one `asyncio.Task` per accepted connection (R-2).
3. Runs the framing-decode + message-dispatch loop entirely inside
   the per-device task.

Stopping the listener (via `EsphomeTransport.stop()`) MUST cancel all
device tasks within 1 second and close their sockets cleanly.

---

## 2. Wire-protocol fidelity (subset)

Every message exchanged on the wire is a varint-length-prefixed
protobuf payload from `aioesphomeapi.api_pb2`. The transport
implements the **subset** documented in
[data-model.md § 4](../data-model.md#4-wire-shape-contracts-esphome-subset).

Key invariants:

- **Framing**: `aioesphomeapi.core.make_plain_text_packets()` is the
  exclusive source for outbound serialization; the inverse path uses
  `aioesphomeapi.core.bytes_to_varuint()` for length-prefix decode.
  No hand-rolled framing.
- **Unknown messages**: MUST be silently dropped (logged at DEBUG).
  An ESPHome protocol bump must NOT crash the gateway.
- **Connection lifecycle**: the device's `HelloRequest` arrives first;
  the gateway responds with `HelloResponse`. Then `ConnectRequest` /
  `AuthenticationRequest` (whichever the device sends — newer
  firmware uses `Connect`, older uses `Authentication`). Auth failure
  closes the socket with a `DisconnectResponse`.

---

## 3. Authentication

- **Mode**: plaintext API key (the `password` field of
  `ConnectRequest` / `AuthenticationRequest`).
- **Per-device keys**: stored at `~/.aivg/devices/keys.json` (mode
  0600). One key per device_id.
- **Bootstrap**: `transports.esphome_api.bootstrap_key` (optional
  config) allows an unregistered device to complete one
  Connect+Auth cycle so the operator can adopt it via `aivg device
  adopt <device_id>` — same adopt flow WebRTC devices use.
- **Failure**: an unauthenticated message after Hello → MUST send
  `DisconnectResponse` and close. Logged at INFO with `source:
  "esphome"`, `reason: "auth_failed"`.

---

## 4. Voice-pipeline contract

Per turn:

1. Device sends `VoiceAssistantRequest` (start-of-pipeline signal).
2. Gateway emits `VoiceAssistantResponse` (acknowledgement, includes
   negotiated audio format).
3. Device sends a stream of `VoiceAssistantAudio` frames carrying
   raw PCM16 mono @ 16 kHz.
4. Gateway emits `VoiceAssistantEventResponse` events per the R-4
   mapping table — `STT_START` when first audio arrives, `STT_END`
   when the **server-side** `AgentPlatform.endpoint(frame)` returns
   `end_of_utterance=True`, `INTENT_START`/`_END`, `TTS_START`,
   then outbound `VoiceAssistantAudio` frames (resampled to 16 kHz
   from the platform's 48 kHz internal), then `TTS_END` and
   `RUN_END`.
5. The device's own STT_END event is **informational only** — the
   gateway's server-side endpoint detector is authoritative
   (Principle I).

The mapping is binding for v1.0.0 of the transport; firmware that
expects events in a different order may need a wrapper feature
(not v1).

---

## 5. `MediaTransport` adapter contract

`EsphomeMediaTransport` MUST satisfy every member of the
`MediaTransport` Protocol defined in
`src/aivg_core/webrtc/session.py:70-83`:

```python
class MediaTransport(Protocol):
    async def receive(self) -> Optional[bytes]: ...
    async def send_audio(self, pcm: bytes) -> None: ...
    async def stop_playback(self) -> None: ...
    @property
    def connection_state(self) -> str: ...
    async def close(self) -> None: ...
```

Binding semantics:

- `receive()` returns PCM16 mono @ **48 kHz**, framed at 20 ms
  (1920 bytes), matching `webrtc.AiortcTransport.receive()`.
  Resampling from 16 kHz wire is internal.
- `send_audio(pcm)` accepts PCM16 mono @ 48 kHz and internally
  resamples to 16 kHz before wrapping in `VoiceAssistantAudio`
  outbound frames.
- `stop_playback()` drains the outbound queue without sending —
  matches WebRTC's `stop_playback` semantics for barge-in.
- `close()` is idempotent (C7). Subsequent `receive()` calls return
  `None` immediately.

A unit test under
`tests/unit/test_esphome_media_adapter.py` MUST prove the Protocol
membership and the resampling round-trip
(48 kHz → 16 kHz → 48 kHz error ≤ tolerable PCM dB).

---

## 6. Constitutional Principle IV preservation

- ZERO modifications to `src/aivg_core/platforms/`. Grep gate:
  `git diff main -- src/aivg_core/platforms/` returns zero lines
  for this feature (SC-003).
- ZERO modifications to `src/aivg_core/webrtc/session.py`. The
  new transport adapts to the existing `MediaTransport` Protocol;
  no `Session` edits are part of this feature.
- The new transport calls `AgentPlatform` verbs **only** through
  `Session`. It MUST NOT import `aivg_core.platforms.*` directly.

A grep-gate regression test under
`tests/unit/test_no_transport_imports_in_platforms.py` (SC-005)
binds it.

---

## 7. Wire-surface invariance (FR-002, SC-002)

This feature changes ZERO bytes on:

- The HTTP `/devices/register`, `/devices/{id}/*` endpoints.
- The management-plane WS subscribe/state/command frames.
- The HTTP `/webrtc/offer` request/response.
- The voice-plane WebRTC SDP offer/answer.
- The TypeScript SDK (`@aivg/sat-sdk`) public API.

The **only** wire-surface change is:

- `aivg --contract-version` envelope: `"1.0.0"` → `"1.1.0"`, plus a
  new `transports: ["webrtc", "esphome_api"]` field. Minor bump
  (additive); same-major-version compatibility check (which the TS
  SDK already does) passes.

A working v0.1.x SDK build MUST continue to drive the gateway over
a live WebRTC session through every code path touched by this
feature. Enforced by re-running the electron-test smoke
(feature 014 / SC-002).

---

## 8. Contract tests (binding)

| Test | What it asserts | Source FR |
|---|---|---|
| `test_esphome_framing.py::test_varint_roundtrip` | A representative selection of `api_pb2` messages encode + decode losslessly via `aioesphomeapi.core` | FR-001, R-1 |
| `test_esphome_framing.py::test_unknown_opcode_ignored` | Unknown opcodes are dropped without error (DEBUG log only) | edge |
| `test_esphome_auth.py::test_valid_api_key_accepted` | A device whose key matches the keystore entry passes auth | FR-010, FR-011 |
| `test_esphome_auth.py::test_invalid_key_disconnects` | Mismatched key → `DisconnectResponse` + socket closed | FR-010 |
| `test_esphome_media_adapter.py::test_protocol_membership` | `isinstance(esphome_mt, MediaTransport)` (structural) — Protocol surface satisfied | FR-009 |
| `test_esphome_media_adapter.py::test_resample_roundtrip` | 48 k → 16 k → 48 k round-trip RMS error within budget | resampling |
| `test_esphome_transport_basic.py::test_one_turn_against_echo_platform` | Drive one voice turn end-to-end against the echo platform fixture; ZERO Hermes import in the test | FR-018, SC-004 |
| `test_esphome_multi_device.py::test_four_concurrent_turns` | 4 simulated devices, each completes a turn; per-device latency ≤ 1.5× single-device | SC-006, FR-021 |
| `test_esphome_disconnect_cleanup.py::test_no_task_leak` | 100 sessions opened-and-dropped; open-task count returns to baseline within 5 s | SC-007, FR-021 |
| `test_no_transport_imports_in_platforms.py::test_no_transport_imports_in_platforms` | grep `from .*transports/esphome` under `src/aivg_core/platforms/` → zero matches | SC-005 |

The full suite (existing 290 + new tests) MUST pass at green across
3 consecutive runs (mirrors feature-015's stability bar).

---

## 9. Out of scope for this contract

- TLS / Noise-encryption transport (v1.1 follow-up).
- ESPHome entities (sensors, buttons) — we expose none.
- The `VoiceAssistantAnnounceRequest` out-of-turn TTS push (v1.1).
- Timer events (`VoiceAssistantTimerEventResponse`) (v1.1).
- mDNS service discovery (OOS-003).
- The C++ SDK (feature 016, ships after 017).
