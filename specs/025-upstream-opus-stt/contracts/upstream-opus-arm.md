# Contract: upstream Opus mic arm

**Contract**: `aivg.satellite.v1` · **Change**: additive · **Version**: 0.3.0 → **0.4.0**

Wire-contract change consumed by satellite SDKs. **Additive** — no existing field
changes meaning — so old↔new interoperate on raw PCM.

## Proto delta (`proto/aivg/satellite/v1/audio.proto`)

```diff
 message ClientFrame {
   oneof body {
     SessionHeader session = 1;
     PcmChunk      pcm     = 2;
     ClientEvent   event   = 3;
+    OpusChunk     opus    = 4;  // Opus-encoded 48 kHz mic frame (feature 025)
   }
 }
+
+message OpusChunk {
+  bytes  payload = 1;  // one Opus packet, 20 ms @ 48 kHz mono
+  uint64 ts_ns   = 2;  // capture timestamp (monotonic, ns)
+}

 message SessionHeader {
   string session_id = 1;
   repeated Codec downstream_codec_pref = 2;
+  repeated Codec upstream_codec_pref   = 3;  // best-first mic codec (feature 025)
 }
```

Register/adoption reply (management plane) gains an additive
**upstream-Opus acceptance** signal (WS JSON field for the C++ control plane;
`RegisterReply` field for the gRPC `Management` service).

Regenerate **Python** stubs (`scripts/gen_proto.sh`) and **C++** stubs.

## Negotiation + handshake

1. **Register** (device→gateway, control plane): device advertises capability;
   gateway replies with `chosen_transport` **and** an upstream-Opus acceptance
   signal. The device reads this **before** opening the Audio.Stream.
2. **Pick mode** (device): if accepted + opted-in → upstream = Opus (capture
   48 kHz, `mic_frame_samples()==960`); else → PCM (16 kHz, `==320`). Set once per
   session.
3. **SessionHeader** (device→gateway, Audio.Stream): includes
   `upstream_codec_pref` (informational/confirmation).
4. **Stream** (device→gateway): the device sends `opus` frames (Opus path) or
   `pcm` frames (PCM path). The gateway dispatches on the arm and decodes Opus →
   48 kHz → STT.

## Behavioral contract (gateway)

| `ClientFrame` arm received | Gateway action | STT input |
|----------------------------|----------------|-----------|
| `opus` | decode Opus → 48 kHz → Session | 48 kHz |
| `pcm` | 16→48 upsample → Session (unchanged) | 48 kHz |
| `opus` but malformed/undecodable | drop the packet, session continues (FR-007) | — |
| `opus` on an **old** gateway | unknown arm → ignored (handshake prevents the device from sending it) | — |

## Compatibility matrix

| | New gateway (accepts Opus up) | Old gateway (0.3.x) |
|---|---|---|
| **New device** (can send Opus) | Opus mic uplink, decoded → STT ✅ | no acceptance signal → device sends raw PCM ✅ |
| **Old device** (PCM only) | raw PCM (unchanged) ✅ | raw PCM (unchanged) ✅ |

No combination errors; the worst case is the existing raw-PCM uplink.

## Test obligations

- **Contract**: `ClientFrame` has an `opus` arm; `OpusChunk` + `SessionHeader.
  upstream_codec_pref` exist (Python contract test; C++ proto test).
- **Gateway**: an `opus` frame is decoded to 48 kHz and reaches STT with a
  transcript equivalent to the PCM path; a malformed `opus` packet is dropped
  without killing the session; the `pcm` path is byte-for-byte unchanged.
- **C++ SDK**: when the gateway advertises acceptance + opt-in → `send_mic` emits
  `opus` arms (`mic_frame_samples()==960`); otherwise emits `pcm`
  (`==320`); inproc test asserts the negotiated arm/rate.
- **Version**: `aivg --contract-version` reports `0.4.0` (3 assertions updated).
- **Bandwidth (SC-002)**: an Opus utterance uploads ≥ ~5× fewer bytes than the
  equivalent raw PCM.

## Non-goals

- Downstream path (feature 024). WebRTC upstream (already Opus). esphome upstream.
- Forcing Opus on devices that can't encode it (raw PCM remains universal).
