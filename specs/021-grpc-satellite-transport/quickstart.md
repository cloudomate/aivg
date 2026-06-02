# Quickstart: gRPC Satellite Transport (feature 021)

How a developer brings up, exercises, and validates the gRPC transport. The
native client lives in `aivg-devices`; this quickstart covers the **gateway
side** (this repo) end-to-end against the in-repo echo test platform — no
hardware required.

## Prerequisites

```sh
# Dev install + the new gRPC deps (added to pyproject.toml by this feature)
uv pip install -e '.[dev]'        # brings grpcio, grpcio-tools, protobuf
```

## 1. Regenerate the Python bindings from the contract

```sh
scripts/gen_proto.sh
# regenerates src/aivg_core/transports/grpc/_generated/{audio_pb2,audio_pb2_grpc,...}.py
# Generated files are checked in; run this only after editing proto/.../*.proto
```

## 2. Enable the transport in config

The gRPC transport is **off by default** (like the esphome transport). Opt in
via the existing `satellite:` block in `~/.hermes/config.yaml`:

```yaml
satellite:
  enabled: true
  transports:
    grpc:
      enabled: true
      host: "0.0.0.0"
      port: 8645          # audio plane (distinct from management 8643 / webrtc 8644)
      tls: "insecure"     # trusted-LAN default; "mtls" for fleet (reuses device keystore)
      downstream_codec: "opus"   # or "pcm" (safe Phase-1 fallback)
```

## 3. Run the gateway with the transport mounted

In production the Hermes gateway calls `AivgSatelliteAdapter.start()`; for local
bring-up the integration tests construct it directly. Confirm the gRPC server
binds on `:8645` alongside the management (`:8643`) and WebRTC (`:8644`) sites.

```sh
aivg --contract-version
# after opt-in, expect: {"data": {"contract_version": "0.3.0",
#                                 "transports": ["webrtc","esphome_api","grpc"]}}
```

## 4. Prove a full voice turn over gRPC (echo platform, no hardware)

```sh
pytest tests/integration/test_grpc_transport_basic.py -q
```

What it asserts (mirrors `test_esphome_transport_basic.py`):
1. Transport starts; a fake client opens `Audio.Stream`.
2. Client sends `SessionHeader{session_id}` then streams 16 kHz PCM frames,
   then `ClientEvent{END_OF_UTTERANCE}`.
3. Gateway routes through `Session` → echo platform → returns reply audio.
4. Client receives `ServerEvent{SPEAKING_STARTED}`, `Transcript` frames, and
   `AudioChunk` payloads on the same stream, then `SPEAKING_ENDED`.

## 5. Prove the reliability properties (the whole motivation)

```sh
pytest tests/integration/test_grpc_transport_reconnect.py -q   # FR-019/FR-020
pytest tests/integration/test_grpc_backpressure.py -q          # FR-021
pytest tests/integration/test_grpc_transport_negotiation.py -q # US3 / FR-015..018
```

- **reconnect**: kill the server mid-session → the next "wake" opens a fresh
  stream and completes a turn, with **no** peer renegotiation and **no** manual
  restart (the WebRTC-era watchdog/boot-order workarounds are unnecessary).
- **backpressure**: a deliberately-slow consumer never makes the gateway buffer
  unboundedly; `RESOURCE_EXHAUSTED` is handled cleanly both ends.
- **negotiation**: a client advertising `["grpc","webrtc"]` is served gRPC; a
  WebRTC-only (browser) client is served WebRTC; a legacy esphome client is
  unaffected.

## 6. Inspect with gRPC-native tooling (proves FR-013/FR-023 diagnosability)

```sh
grpcurl -plaintext localhost:8645 list           # server reflection enabled
grpcurl -plaintext localhost:8645 describe aivg.satellite.v1.Audio
```

A stuck link shows a single, clear gRPC status — not a multi-layer ICE/DTLS/SCTP
hunt.

## 7. Phase 2 (after Phase 1 soak): management over gRPC

```sh
pytest tests/integration/test_management_grpc.py -q
# register → adopt → report state → receive command, with /satellite/ws DISABLED
```

## Constitution gates before "supported" (Principle V)

- The gRPC native path MUST pass the **same** end-to-end voice loop the WebRTC
  path passes (echo + a real Hermes host).
- A **≥7-day soak on real hardware** (RPi Zero 2 W class) with zero manual
  restarts attributable to the transport (SC-004) before defaulting native
  satellites to `grpc`.
