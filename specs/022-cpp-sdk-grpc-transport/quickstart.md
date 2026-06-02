# Quickstart: C++ SDK gRPC Transport (feature 022)

How a developer builds, exercises, and validates the gRPC transport in
`libaivg-sat`. The RPi/POSIX tier is the focus (the MVP); ESP32-S3 stays on
WebRTC this feature.

## Prerequisites (RPi / POSIX host)

- A C++17 toolchain + CMake (as feature 020).
- gRPC C++ + protobuf dev packages (RPi OS: `libgrpc++-dev libprotobuf-dev
  protobuf-compiler protobuf-compiler-grpc`; or vcpkg / a gRPC install).
- A running **gRPC-capable gateway** (feature 021 with `transports.grpc.enabled`).

## 1. Regenerate the C++ stubs from the contract (only if proto changed)

```sh
cmake -P sdks/cpp/cmake/GenerateProto.cmake     # or the build target below
# writes sdks/cpp/src/grpc/_generated/audio.pb.* + audio.grpc.pb.*
# (checked in; consumers don't need protoc)
```

## 2. Build the SDK with the gRPC transport

```sh
cmake -S sdks/cpp -B sdks/cpp/build \
  -DAIVG_SAT_ENABLE_VOICE=ON \
  -DAIVG_SAT_LIBPEER_ROOT=/path/to/libpeer \
  -DAIVG_SAT_ENABLE_GRPC=ON              # NEW — POSIX-only; links grpc++/protobuf
cmake --build sdks/cpp/build
```

`AIVG_SAT_ENABLE_GRPC` is off by default and lives in the POSIX branch only — an
ESP-IDF component build never sees grpc++/protobuf (FR-015). A build with it
**off** is byte-for-byte the feature-020 SDK (SC-005).

## 3. Hardware-free seam test (no gateway, no device)

```sh
ctest --test-dir sdks/cpp/build -R transport_seam
```

`tests/test_transport_seam.cpp` drives a real `VoiceSession` against an
in-process `FakeTransport` (enabled by the new seam): asserts mic PCM flows on
`send_mic`, scripted downstream audio reaches the speaker callback, and
`ServerEvent`/`Transcript` surface as the existing `SatEvent`s. Also confirms a
gRPC-disabled build still compiles and the WebRTC path is unchanged.

## 4. Live end-to-end over gRPC (real gateway)

```sh
sdks/cpp/build/grpc_audio_smoke grpc://127.0.0.1:8645 <device_id>
```

`tests/grpc_audio_smoke.cpp` (not a ctest — like `ws_register_smoke`): registers
advertising `transport_capabilities: ["grpc","webrtc"]`, the gateway selects
`grpc`, opens one `Audio.Stream`, streams a short utterance (raw PCM up), and
asserts reply `AudioChunk`s + `Transcript`/`SpeakingStarted` come back — with no
WebRTC offer/answer in the path.

## 5. Prove the reliability win on real RPi hardware

- **Recovery (FR-012)**: restart the gateway mid-idle; the next wake opens a
  fresh `Audio.Stream` and completes a turn — no manual restart, no boot-order
  guard.
- **Latency (SC-003)**: end-of-speech → first reply audio shows no multi-second
  connection-setup step versus the WebRTC build.
- **Negotiation (US3/SC-007)**: a WebRTC-only build (or a pre-021 gateway) still
  completes a turn over WebRTC, unchanged.

## 6. Constitution V gates before "supported"

- **RPi tier**: passes the same end-to-end voice loop the WebRTC path passes,
  plus a **≥7-day soak** with zero transport-attributable restarts (SC-004)
  before native defaults flip to gRPC.
- **ESP32-S3 tier (US2 spike)**: gRPC is adopted there ONLY with recorded
  on-device binary-size + PSRAM/heap-under-full-pipeline measurements and a
  completed on-device turn (FR-008/FR-009/SC-006); otherwise it stays on WebRTC.
  No unmeasured decision ships.
