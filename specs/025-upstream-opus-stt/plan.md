# Implementation Plan: Opus upstream (mic → STT) voice

**Branch**: `025-upstream-opus-stt` | **Date**: 2026-06-04 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/025-upstream-opus-stt/spec.md`

## Summary

Add an **additive Opus mic arm** to the gRPC upstream (device→gateway) path so a
native satellite can compress its mic uplink with Opus instead of streaming raw
16 kHz PCM; the gateway decodes it before STT. Mirrors feature 024 (downstream
Opus) on the other direction.

**Approach** (per the 2026-06-04 clarifications):
- **Wire**: add `OpusChunk opus = 4` to `ClientFrame` (additive oneof arm,
  self-describing) + `upstream_codec_pref` to `SessionHeader`. Regenerate the
  Python and C++ bindings. Additive contract bump **0.3.0 → 0.4.0**.
- **Device (C++ SDK)**: `GrpcTransport::send_mic` Opus-encodes at **48 kHz**
  (OpusBridge, already present) — no on-device decimation. The mic capture rate
  is **negotiation-dependent** (Option C): **48 kHz** when Opus upstream is in
  effect (`mic_frame_samples()==960`), **16 kHz** on PCM fallback (`==320`); **no
  on-device resampler**.
- **Gateway**: the gRPC handler dispatches on the frame arm — `opus` → decode to
  48 kHz → feed the Session exactly like the existing 48 kHz path (STT already
  runs at 48 kHz, so **no separate 16 kHz step is needed**); `pcm` → unchanged.
- **Handshake (Option C needs the device to know acceptance before it picks a
  capture rate)**: the gateway advertises upstream-Opus acceptance at **register
  time** (the control/capability plane the device already reads for
  `chosen_transport`), so the device configures its upstream mode before opening
  the Audio.Stream. The arm itself is self-describing, so the gateway never
  guesses.

**Scope**: the gRPC native tier — gateway (Python) + C++ SDK. WebRTC already
sends Opus upstream; esphome streams Home Assistant's rate (both out of scope).

> **Refinement of the clarification**: the clarification said "decode → 48 kHz →
> resample to 16 kHz → STT", on the assumption STT runs at 16 kHz. The gateway
> actually feeds STT at **48 kHz** (`session.py` passes `sample_rate=48000`), and
> the existing raw-PCM path upsamples 16→48 before STT. So the Opus path decodes
> to 48 kHz and joins the existing pipeline — the redundant 48→16→48 round trip is
> omitted. This preserves the intent (equivalent transcripts) and is simpler;
> flagged for confirmation.

## Technical Context

**Language/Version**: Python ≥ 3.11 (gateway `aivg_core`); C++17 (`sdks/cpp`);
canonical proto under `proto/aivg/satellite/v1/`
**Primary Dependencies**: PyAV libopus (gateway decode — already a dep, used by
024); `audioop` (existing reframe); `grpcio`/`protobuf` (regen via
`scripts/gen_proto.sh`); C++ `OpusBridge` (libopus encode — already present) +
`grpc++`
**Storage**: N/A
**Testing**: `pytest` + `pytest-asyncio` (gateway); C++ `ctest` in the
`rpi-builder` container (gRPC needs `grpc++`)
**Target Platform**: Linux gateway; native gRPC satellites (RPi-class)
**Project Type**: Single Python gateway + the C++ SDK + a versioned wire contract
**Performance Goals**: Real-time voice; ~5×+ smaller mic uplink (SC-002); no added
turn latency; Opus encode on RPi is cheap
**Constraints**: Additive wire change (old↔new interoperate on raw PCM); the
device must learn upstream-Opus acceptance before streaming (Option C); STT
quality unchanged; bounded queues preserved
**Scale/Scope**: proto arm + gateway decode + register-capability signal + C++
SDK upstream mode + regen (Python & C++) + contract bump + tests. Multi-component
but each piece is small and mirrors an existing pattern (024 downstream Opus).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Thin Satellite, Gateway-Owned Intelligence** — ✅ PASS. The device
  **Opus-encodes its mic** — transport compression, exactly like the WebRTC path
  already does upstream; it is NOT STT. No STT/agent logic moves to the device.
  **Note**: feature 022 R-3 deferred on-device Opus encode on the gRPC path for
  the MVP/ESP32; this feature enables it for the **RPi-class gRPC tier** (ample
  CPU). ESP32 stays on WebRTC (gRPC is POSIX-only), so the constraint that drove
  R-3 is not violated — documented in Complexity Tracking.
- **II. Generic Four-Plane Contract (no `device_type` branching)** — ✅ PASS. The
  upstream codec is negotiated **per session** via a preference + a self-
  describing frame arm, not by branching on `device_type`. The gateway core
  treats all devices identically.
- **III. Separate Control and Voice Connections + capability negotiation** —
  ✅ PASS / reinforces. Upstream-Opus *acceptance* rides the **control/register
  capability** plane (where `chosen_transport`/transport capabilities already
  negotiate), keeping durable capability state off the per-session voice stream.
  The voice stream just carries the agreed arm.
- **IV. Reuse the Upstream Agent Platform** — ✅ PASS. STT is unchanged; the
  gateway only decodes mic audio to the form STT already consumes (48 kHz).
- **V. Research-Backed, Constraint-Driven Decisions** — ✅ PASS. On-device Opus
  encode is justified by the **RPi-class CPU headroom** of the gRPC tier (vs the
  ESP32 constraint that deferred it). Per Principle V it MUST be proven
  **end-to-end** on real hardware (live gate: a real utterance transcribed
  correctly from Opus upstream, with a measured uplink-bytes reduction).

**Result**: PASS — one documented deviation (enabling on-device gRPC Opus encode,
reversing 022 R-3 for the RPi tier), justified by tier; see Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/025-upstream-opus-stt/
├── plan.md
├── research.md          # Phase 0 — wire arm, handshake design, STT-rate refinement, 022 R-3 reversal
├── data-model.md        # Phase 1 — upstream codec/arm entities + capture-rate state
├── quickstart.md        # Phase 1 — tests + the Principle V live gate (Opus mic → transcript on iva)
├── contracts/
│   └── upstream-opus-arm.md   # the additive proto delta + register-capability + compat matrix
└── tasks.md             # /speckit-tasks (NOT created here)
```

### Source Code (repository root)

```text
proto/aivg/satellite/v1/
├── audio.proto                 # CHANGED — add OpusChunk opus = 4 to ClientFrame;
│                               #   add upstream_codec_pref to SessionHeader (additive)
└── management.proto            # CHANGED (if needed) — advertise upstream-Opus acceptance
                                #   in the register/adoption capability reply

src/aivg_core/transports/grpc/
├── _generated/                 # REGENERATED (Python) via scripts/gen_proto.sh
├── stream_handler.py           # CHANGED — dispatch the `opus` arm -> adapter.push_inbound_opus
├── media_adapter.py            # CHANGED — push_inbound_opus(): decode Opus -> 48 kHz -> _in
│                               #   (reuses the 20 ms reframe; raw-PCM push_inbound unchanged)
├── codec.py                    # REUSE — Opus decode helper (mirror of the 024 encoder)
└── management_service.py       # CHANGED (if mgmt-plane signal) — advertise upstream-Opus

src/aivg_cli/cli.py             # CHANGED — CONTRACT_VERSION 0.3.0 -> 0.4.0 (additive)

sdks/cpp/
├── src/grpc/_generated/        # REGENERATED (C++) from the proto
├── src/transport/grpc_transport.{hpp,cpp}  # CHANGED — send_mic Opus-encodes (OpusBridge);
│                               #   mic_frame_samples() negotiation-dependent (960|320);
│                               #   send the `opus` arm; advertise upstream_codec_pref
├── include/aivg/sat/satellite.hpp + src/satellite.cpp  # CHANGED — grpc_upstream_opus option;
│                               #   read the gateway's upstream-Opus acceptance from register
└── src/control_plane.*         # CHANGED (if mgmt-plane signal) — parse upstream-Opus acceptance

tests/  (Python) + sdks/cpp/tests/  # unit + integration + C++ inproc, mirroring 024
```

**Structure Decision**: Single Python gateway + the C++ SDK + the shared proto.
The change mirrors feature 024 on the upstream direction and reuses the existing
capability-negotiation seam for the acceptance handshake. The Opus decode reuses
PyAV/libopus (already a gateway dep); the device encode reuses `OpusBridge`
(already present for WebRTC).

## Complexity Tracking

| Deviation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Enable **on-device Opus encode on the gRPC path** (reverses feature 022 R-3) | The feature's whole point is compressing the mic uplink; the gRPC tier is RPi-class with ample CPU (R-3 deferred it only for the ESP32/MVP constraint, and ESP32 stays on WebRTC) | Keeping raw-PCM-only upstream would not deliver the bandwidth benefit at all |
| **Register-time acceptance handshake** (capability signal before the voice stream) | Option C requires the device to pick its capture rate (48 k vs 16 k) *before* it starts streaming, so it must know acceptance up front | A SessionHeader-only / on-stream ack arrives after the device has already committed to a capture rate (chicken-and-egg) |
