# Implementation Plan: Negotiated downstream PCM sample rate (gRPC)

**Branch**: `024-downstream-rate-negotiation` | **Date**: 2026-06-03 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/024-downstream-rate-negotiation/spec.md`

## Summary

The gRPC downstream (gateway→device) PCM wire is fixed at 16 kHz, so a 48 kHz
device suffers a lossy **48 kHz → 16 kHz (gateway) → 48 kHz (device)**
double-resample. The gateway's pipeline is already 48 kHz, so 48 kHz downstream
is the *no-resample* path. This feature lets a device **advertise** a downstream
PCM rate and the gateway **honor** it.

**Approach**: reuse the existing downstream-codec negotiation verbatim by adding
one **additive** `Codec` enum value `CODEC_PCM_S16LE_48K` to the canonical proto.
The device advertises it in the existing `SessionHeader.downstream_codec_pref`
(best-first); the gateway's existing `select_downstream_codec` picks it (it is
always producible — the pipeline is native 48 kHz); the existing per-chunk
`AudioChunk.codec` stamp labels it. The only behavioral change is in the gateway
outbound pump: when the negotiated codec is 48 kHz PCM, **skip the 48→16
downsample** and pass the native 48 kHz audio straight to the wire. Everything
else (negotiation, labeling, fallback, the 16 kHz default) is inherited
unchanged, so existing 16 kHz devices are byte-identical and version skew is
safe.

**Scope**: gateway + canonical contract (Python), validated with a gRPC test
client that advertises 48 kHz. Client/device *adoption* (the C++ SDK /
rpi-pipewire advertising 48 kHz and playing it natively) is out of scope per the
spec and noted as the consuming follow-on.

## Technical Context

**Language/Version**: Python ≥ 3.11 (gateway `aivg_core`); canonical proto under
`proto/aivg/satellite/v1/`
**Primary Dependencies**: `grpcio` + `protobuf` (generated stubs, regenerated via
`scripts/gen_proto.sh`); stdlib `audioop` (existing downsample, now conditional);
PyAV (feature-023 decode, unchanged)
**Storage**: N/A
**Testing**: `pytest` + `pytest-asyncio` — `tests/unit/test_grpc_codec.py`,
`tests/unit/test_grpc_media_adapter.py`, `tests/contract/test_grpc_contract.py`,
`tests/integration/test_grpc_transport_basic.py`
**Target Platform**: Linux gateway (server-side); native gRPC satellites (RPi)
**Project Type**: Single Python project (`src/aivg_core/`) + a versioned wire
contract consumed by multiple SDKs
**Performance Goals**: Real-time voice; the 48 kHz path does **less** work
(removes a resample stage) — 3× the PCM bytes/sec on the wire (16 k→48 k) but no
CPU resample
**Constraints**: Fully additive wire change (no existing field changes meaning);
old client↔new gateway and new client↔old gateway both interoperate at 16 kHz;
per-chunk rate label must always match payload; bounded queues preserved
**Scale/Scope**: 1 proto enum value + ~1 conditional in the pump + selection
producibility + contract-version bump + tests. Small, additive.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Thin Satellite, Gateway-Owned Intelligence** — ✅ PASS. Gateway-side audio
  *plumbing* (resample vs. passthrough), not STT/TTS. No engine introduced.
- **II. Generic Four-Plane Contract (no `device_type` branching)** — ✅ PASS /
  strengthens. The new rate is negotiated via a per-session **preference**, not by
  branching on `device_type`; the gateway selects by "best producible" exactly as
  it does for codecs today. The shared contract is extended uniformly for all
  device types. It removes a fixed bottleneck rather than adding a special case.
- **III. Separate Control and Voice Connections** — ✅ PASS. Voice-plane audio
  *content/format* only; no change to connection topology or `Audio.Stream`
  framing.
- **IV. Reuse the Upstream Agent Platform** — ✅ PASS. No platform/TTS change; the
  gateway re-formats audio the platform already produced.
- **V. Research-Backed, Constraint-Driven Decisions** — ✅ PASS, and directly
  motivated by a binding hardware constraint: the **ReSpeaker XVF3800** ships an
  *"I2S 48 kHz master firmware variant only"* (Constitution → Hardware & Platform
  Constraints), so 48 kHz is the device-native rate and the 16 kHz wire is a pure
  loss for it. Per Principle V the 48 kHz path MUST be proven **end-to-end** on
  real 48 kHz hardware (captured as the quickstart live gate).

**Result**: PASS — no violations, no Complexity Tracking entries.

## Project Structure

### Documentation (this feature)

```text
specs/024-downstream-rate-negotiation/
├── plan.md              # this file
├── research.md          # Phase 0 — wire-shape decision, passthrough, contract bump
├── data-model.md        # Phase 1 — the negotiated-format entities + rate label invariant
├── quickstart.md        # Phase 1 — test + the Principle V 48 kHz live gate (iva)
├── contracts/
│   └── audio-codec-48k.md   # the additive proto delta + negotiation contract
└── tasks.md             # /speckit-tasks (NOT created here)
```

### Source Code (repository root)

```text
proto/aivg/satellite/v1/
└── audio.proto                       # CHANGED — add CODEC_PCM_S16LE_48K = 3 (additive)

src/aivg_core/transports/grpc/
├── _generated/                       # REGENERATED via scripts/gen_proto.sh (Python stubs)
├── codec.py                          # CHANGED — CODEC_PCM_S16LE_48K alias; producible=True;
│                                     #   encode() passthrough; name map "pcm48k"
├── media_adapter.py                  # CHANGED — run_outbound_pump: skip 48→16 downsample
│                                     #   when codec is 48 kHz PCM (passthrough), else as today
└── stream_handler.py                 # UNCHANGED — already threads the selected codec

src/aivg_cli/cli.py                   # CHANGED — CONTRACT_VERSION "0.3.0" -> "0.4.0" (additive)

tests/
├── unit/test_grpc_codec.py           # +select 48k when preferred / producible
├── unit/test_grpc_media_adapter.py   # +48k negotiated => no downsample, full-band payload
├── contract/test_grpc_contract.py    # +CODEC_PCM_S16LE_48K exists in the enum
├── integration/test_grpc_transport_basic.py  # +a turn advertising 48k => 48 kHz chunks
└── unit/{test_cli_help_contract,test_cli_tagline}.py + integration/test_install_from_built_wheel.py
                                       # CHANGED — contract-version assertions 0.3.0 -> 0.4.0
```

**Structure Decision**: Single Python gateway plus the canonical proto contract.
The change is deliberately tiny because it **reuses** the existing
codec-negotiation machinery — the new rate is just another `Codec` value. The
C++ SDK's checked-in stubs and downstream handling are NOT touched here (client
adoption is a separate consuming change; the additive enum leaves old C++ stubs
compiling — they map the unknown value to `Unspecified`).

## Complexity Tracking

> No Constitution Check violations — section intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| (none) | — | — |
