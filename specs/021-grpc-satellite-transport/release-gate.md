# Release Gate: defaulting native satellites to gRPC (feature 021)

**Status**: gate OPEN — must pass before flipping any native satellite's
default transport from `webrtc` to `grpc`.

Constitution **Principle V** ("Research-Backed, Constraint-Driven Decisions")
requires that a transport decision affecting constrained hardware be **validated
before it is relied on**, and that heavy-pipeline targets be load-tested with
the *full* pipeline running together — not component-by-component. The gRPC
transport is proven in-process (echo platform, 40 tests) but **not** yet on real
hardware under sustained load. This gate records what must be true first.

## What this gate blocks

- Changing the gateway default / negotiation preference so a native satellite
  that advertises both transports is steered to `grpc` in production.
- Removing the WebRTC native path or the boot-order/watchdog workarounds for any
  fleet device.

It does **not** block: shipping the transport as opt-in (`transports.grpc.enabled`),
which is already safe — operators choose it explicitly per deployment.

## Soak checklist (must all hold)

- [ ] **≥7-day continuous soak** on a real RPi Zero 2 W-class satellite running
      the full pipeline (wake word + VAD + capture + gRPC + playback + OS),
      against a real Hermes gateway — **zero** manual restarts attributable to
      the transport (SC-004).
- [ ] **End-to-end voice loop parity** with the WebRTC path on real hardware:
      the gRPC native path passes the same end-to-end loop the WebRTC path
      passes (Principle V / Development-Workflow quality gate).
- [ ] **Recovery proven on hardware**: gateway restart, network blip, and
      boot-before-gateway each recover on the next turn with no operator action
      (FR-019/FR-020) — observed on the device, not just in tests.
- [ ] **Backpressure on a constrained device**: a slow Pi never desyncs audio or
      grows memory without bound under a long reply (FR-021).
- [ ] **Latency measured**: end-of-speech → first-reply-audio on hardware shows
      the WebRTC per-session negotiation overhead (~1 s) is gone (SC-003).
- [ ] **ESP32-S3 tier** (if targeted) exercised against the same loop before it
      is declared supported.

## Evidence

Record soak results (dates, device, gateway, restart count, latency numbers)
here or in the companion `aivg-devices` repo's deploy notes, and link from this
file, before checking the boxes above and proposing the default flip.
