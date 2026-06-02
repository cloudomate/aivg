# Release Gate: defaulting native satellites to gRPC (feature 022, C++ SDK)

**Status**: gate OPEN — must pass before changing the **default** transport of
any shipped `libaivg-sat` satellite from WebRTC to gRPC.

Constitution **Principle V** requires a transport decision affecting constrained
hardware to be **validated before it is relied on**, with heavy-pipeline targets
load-tested with the *full* pipeline running together. The gRPC transport is
proven in-process (rpi-builder arm64: seam test + in-process round-trip) but not
yet on real hardware under sustained load. This gate records what must hold first.

## What this gate blocks

- Changing the SDK/operator default so a satellite that advertises both
  transports is steered to gRPC in production by default.
- Removing the WebRTC native path or the boot-order/watchdog workarounds.

It does **not** block shipping gRPC as opt-in (`SatelliteOptions.transport` /
`AIVG_SAT_ENABLE_GRPC`) — operators choose it explicitly per build/deployment.

## RPi/POSIX tier (US1) — soak checklist

- [ ] **≥7-day continuous soak** on a real RPi Zero 2 W-class satellite running
      the full pipeline (wake word + capture + gRPC + playback) against a real
      gateway — **zero** manual restarts attributable to the transport (SC-004).
- [ ] **Voice-loop parity** with WebRTC on real hardware (the gRPC native path
      passes the same end-to-end loop the WebRTC path passes).
- [ ] **Recovery on hardware**: gateway restart, network blip, and
      boot-before-gateway each recover on the next turn with no operator action
      (FR-012), observed on the device.
- [ ] **Latency on hardware**: end-of-speech → first reply audio shows the
      WebRTC per-session negotiation overhead is gone (SC-003).

## ESP32-S3 tier (US2)

Governed separately by [esp32-grpc-spike.md](./esp32-grpc-spike.md): on-device
gRPC is adopted only with recorded binary-size + PSRAM/heap-under-full-pipeline
measurements and a completed on-device turn; otherwise the tier stays on WebRTC.

## Evidence

Record soak/latency results (dates, device, gateway, restart count, numbers)
here or in the `aivg-devices` deploy notes and link from this file before
checking the boxes and proposing the default flip.
