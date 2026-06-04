# Data Model: Opus upstream (mic → STT) voice

No persisted entities. The "data" is the additive wire delta and the in-flight
upstream-audio format/state. All wire changes are **additive**.

## Wire contract delta (additive)

### `ClientFrame` — new self-describing arm
```
message ClientFrame {
  oneof body {
    SessionHeader session = 1;  // first frame ONLY
    PcmChunk      pcm     = 2;  // raw 16 kHz int16 LE mono, 20 ms (640 B)
    ClientEvent   event   = 3;  // wake / end-of-utterance / barge-in
    OpusChunk     opus    = 4;  // NEW — Opus-encoded 48 kHz mic frame (feature 025)
  }
}

message OpusChunk {
  bytes  payload = 1;  // one Opus packet (20 ms @ 48 kHz mono, encoded on-device)
  uint64 ts_ns   = 2;  // capture timestamp (monotonic, ns) — mirrors PcmChunk
}
```

### `SessionHeader` — new upstream preference (mirrors downstream)
```
message SessionHeader {
  string session_id = 1;
  repeated Codec downstream_codec_pref = 2;   // existing
  repeated Codec upstream_codec_pref   = 3;   // NEW — best-first mic codec the device will send
}
```

### Register/adoption reply — new acceptance signal
An additive field advertising that the gateway **accepts upstream Opus** (e.g. an
`upstream_opus` bool or an `audio_capabilities` list), carried on the reply the
device already reads for `chosen_transport` (WS JSON for the C++ control plane;
`RegisterReply` for the gRPC `Management` service).

- **Backward compatibility**: proto3 open enum/fields. Old gateways never set the
  acceptance signal and ignore the unknown `opus` arm; old devices never send it.

## Audio-format invariants

| Direction / mode | Wire | Device | Gateway |
|------------------|------|--------|---------|
| Upstream PCM (default/legacy) | `pcm` (16 kHz s16, 640 B) | capture 16 kHz, no encode | `push_inbound` 16→48 → Session |
| Upstream **Opus** (NEW) | `opus` (48 kHz Opus packet) | capture 48 kHz, `OpusBridge::encode` | `push_inbound_opus`: decode → 48 kHz → Session |
| STT input (unchanged) | — | — | 48 kHz s16 mono (`transcribe(sample_rate=48000)`) |

**Invariant**: the gateway dispatches strictly on the `ClientFrame` arm; the
device sends only the arm matching the negotiated upstream mode. STT receives
48 kHz either way (FR-002/003).

## Entities (conceptual)

- **Upstream codec preference** — `SessionHeader.upstream_codec_pref`, best-first;
  MAY contain `CODEC_OPUS`. Default/empty ⇒ raw PCM.
- **Upstream acceptance signal** — gateway→device capability ("accepts upstream
  Opus") delivered at register, consumed before the voice session.
- **Negotiated upstream mode** — per session: Opus (48 kHz capture, `opus` arm) or
  PCM (16 kHz capture, `pcm` arm); raw PCM is the universal fallback.
- **Opus mic frame** — one 20 ms Opus packet (48 kHz mono); decoded gateway-side.

## State / selection rules

- **Device** (C++ SDK): if the gateway advertised upstream-Opus AND
  `grpc_upstream_opus` is enabled → upstream mode = Opus (`mic_frame_samples()`
  = 960, `send_mic` encodes the `opus` arm); else PCM (`==320`, `pcm` arm). Set
  **once per session**, before the mic pump starts.
- **Gateway**: dispatch per frame on `WhichOneof("body")` — `opus` →
  `push_inbound_opus` (decode); `pcm` → `push_inbound` (unchanged); `event`/
  `session` unchanged. A malformed Opus packet is dropped (FR-007), session lives.
- **Fallback** (FR-004/006): no acceptance signal, or device opts out / can't
  encode → raw PCM upstream, transcribed as today.

## Components touched

- `audio.proto` (+ Python & C++ regen) — `OpusChunk`, `opus` arm,
  `upstream_codec_pref`.
- gateway `stream_handler.py` (dispatch `opus`), `media_adapter.py`
  (`push_inbound_opus` + a stateful PyAV libopus decoder), `codec.py` (decode
  helper), register/`management_service.py` (advertise acceptance), `cli.py`
  (contract 0.4.0).
- C++ SDK `grpc_transport.{hpp,cpp}` (`send_mic` encode + dynamic
  `mic_frame_samples` + `opus` arm), `satellite.{hpp,cpp}` (`grpc_upstream_opus`
  option + read acceptance), `control_plane.*` (parse acceptance), `OpusBridge`
  (reused).
