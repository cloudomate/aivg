# ESP32-S3 gRPC transport — spike plan & decision record

**Tasks**: US2 / T018 (spike plan + acceptance bar) and T019 (execute on hardware).
**Status**: decision **deferred to WebRTC** for this feature; on-device gRPC is
gated on the measured spike below. T018 (this plan) is complete; T019 (the
on-hardware measurement) is **pending real ESP32-S3 hardware** — it cannot be
run from CI or the rpi-builder container.

## Decision (current)

**ESP32-S3 stays on WebRTC/libpeer.** The gRPC transport ships RPi/POSIX-tier
first (US1). The build already enforces this (T017): the `if(ESP_PLATFORM)`
branch never defines `AIVG_SAT_HAVE_GRPC`, never lists grpc++/protobuf in
`REQUIRES`, and so `satellite.cpp`'s gRPC branch is `#ifdef`-excluded and the
device advertises only `transport_capabilities: ["webrtc"]`.

This is the Constitution V default: **do not adopt an unmeasured path on the
constrained target.** Adopting on-device gRPC requires passing the bar below.

## Why full gRPC C++ is not an option here

`grpc++` (the official gRPC C++ library) does not build for ESP-IDF and is
server-scale (its own event engine, threads, large transitive deps; MB-class
binary). It cannot fit an ESP32-S3 app partition alongside wake word + capture
+ the existing voice pipeline. So the only candidate for an on-device gRPC path
is a **minimal HTTP/2 + compact-protobuf client**, not `grpc++`.

## The candidate path (if the spike is run)

- **Protobuf**: `nanopb` (tens of KB, no malloc/STL) generating the
  `aivg.satellite.v1` `ClientFrame`/`ServerFrame` messages.
- **Transport**: a hand-rolled minimal HTTP/2 client over the existing TLS/TCP,
  framing only the gRPC subset we need (one bidi stream, length-prefixed
  `DATA` frames, trailers). gRPC's HTTP/2 wire format is documented and small
  in this subset.
- Reuse the existing `Transport` seam (feature 022) — an `EspGrpcTransport`
  implementing the same interface as `GrpcTransport`, so `VoiceSession` is
  unchanged.

## Acceptance bar (T019 — all must hold, with recorded numbers)

A measured PASS is required before flipping ESP32-S3 to gRPC. An unmeasured
guess is a FAIL.

- [ ] **Binary fit**: the firmware image with the gRPC path **fits the device's
      app partition** with margin. Record: image size before/after, partition size.
- [ ] **RAM/PSRAM headroom under load**: free heap + PSRAM stay within budget
      with the **full pipeline running together** (wake word + capture +
      transport + playback), not idle. Record: free-heap low-water mark.
- [ ] **On-device turn**: a real voice turn completes over the gRPC path on the
      device (mic → reply audio), at parity with the WebRTC path.
- [ ] **Recovery**: gateway restart / network blip recovers on the next turn
      (FR-012), observed on the device.

If any fails: **ESP32-S3 stays on WebRTC** and that outcome is recorded here
with the measured numbers (also a valid completion of US2 — SC-006).

## How to run (when hardware is available)

Use the device firmware rig in the companion `aivg-devices` repo
(`devices/respeaker-xvf3800-esp32s3`), which consumes this component via a
path dependency. Build two images (WebRTC baseline vs. the nanopb+HTTP/2
candidate), flash, and record the four metrics above against a live
gRPC-capable gateway.

## Evidence log

_(empty — fill with measured numbers when T019 runs on hardware.)_
