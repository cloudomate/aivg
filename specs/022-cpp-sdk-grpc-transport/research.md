# Phase 0 Research: C++ SDK gRPC Transport

Decisions grounded in the existing `libaivg-sat` code (feature 020) and the
feature-021 contract. Format per item: **Decision / Rationale / Alternatives**.

---

## R-1 — The transport seam: introduce an abstract `Transport` interface

**Decision**: Add `src/transport/transport.hpp` — an abstract interface at the
**audio/lifecycle/event** altitude (NOT SDP). Refactor the existing
`LibpeerTransport` to implement it (no behaviour change) and add `GrpcTransport`
as a sibling. `VoiceSession` holds `std::unique_ptr<Transport>` instead of a
concrete `LibpeerTransport` member.

Proposed interface (see contracts/transport-interface.md for the full contract):
```cpp
class Transport {
 public:
  using OnRemoteAudio = std::function<void(const std::uint8_t*, std::size_t, Codec)>;
  using OnEvent       = std::function<void(TransportEvent)>;   // speaking/vad/transcript/drop
  virtual ~Transport() = default;
  virtual bool begin(const std::string& session_id) = 0;  // open the voice link
  virtual void send_mic(const std::int16_t* pcm16, std::size_t samples) = 0;
  virtual bool ready() const noexcept = 0;   // safe to pump mic? (gRPC: stream open)
  virtual void stop() = 0;
  virtual void set_on_remote_audio(OnRemoteAudio) = 0;
  virtual void set_on_event(OnEvent) = 0;
};
```

**Rationale**: Today there is **no seam** — `LibpeerTransport` is concrete and
WebRTC-shaped (`create_offer`/`set_answer_and_run`). The map confirms a clean
add requires this abstraction. Putting the seam at audio+lifecycle (not SDP)
fits both transports: WebRTC's offer/answer becomes an internal detail of
`LibpeerTransport::begin()`; gRPC's stream-open is `GrpcTransport::begin()`.
This is the correct altitude — one `VoiceSession`, two transports — versus
duplicating `VoiceSession` as a `GrpcSession` (fragile, drifts).

**Alternatives**: (a) Duplicate `VoiceSession` — rejected (copy-paste of the
mic-pump/reconnect/event logic, two code paths to maintain). (b) Templatize
`VoiceSession<Transport>` — rejected (no runtime selection; the device must
pick a transport from negotiation at runtime, so a virtual interface is right).

---

## R-2 — ESP32-S3 tier: stay on WebRTC; gRPC is RPi-tier-first (THE central decision)

**Decision**: For this feature, **ESP32-S3 stays on WebRTC/libpeer**; the gRPC
transport ships **RPi/POSIX-tier only**. The on-device gRPC path for ESP32-S3 is
deferred behind a **measured on-hardware spike** (US2) with a hard acceptance
bar (FR-008/FR-009/SC-006): it is adopted only if a build provably fits the
flash partition and stays within PSRAM/heap under the full running pipeline.

**Rationale** (Constitution V — constraint-driven, validated before relied on):
- The official **gRPC C++ library (`grpc++`) does not target ESP-IDF**: it is a
  server-scale stack (its own event engine, threading, large transitive deps),
  has no FreeRTOS/lwIP port, and its binary footprint is MB-scale — categorically
  too big for an ESP32-S3 app partition alongside wake word + capture + the
  existing voice pipeline. Shipping it there is not viable.
- The *candidate* embedded path is **nanopb** (protobuf in tens of KB) + a
  **hand-rolled minimal HTTP/2 client** framing gRPC manually over the existing
  TLS/TCP (gRPC's HTTP/2 wire format is documented and small in the
  bidi-stream-only subset we need). This is feasible in principle but is
  **substantial new code** whose fit can only be proven by building it and
  measuring binary size + heap on the actual device under load — exactly what
  Constitution V forbids us to assume.
- The ESP32-S3 already has a working WebRTC path (feature 020). Keeping it there
  costs nothing and de-risks this feature: the RPi tier (where gRPC clearly
  fits) delivers the reliability win and proves the design end-to-end first.

**The spike (US2) acceptance bar**: produce either (a) an ESP32-S3 nanopb +
minimal-HTTP/2 gRPC build with recorded binary-size and PSRAM/heap-headroom
numbers showing it fits under the full pipeline AND a completed on-device voice
turn, or (b) a recorded measurement-backed decision to keep ESP32-S3 on WebRTC.
An unmeasured guess fails.

**Alternatives**: (a) Force `grpc++` onto ESP32 — rejected (does not build /
does not fit). (b) Adopt the nanopb+HTTP/2 path now without measuring — rejected
(violates Constitution V; risks shipping a device that OOMs mid-turn). (c) Drop
ESP32 from the SDK — rejected (it is the broader product's MVP-lead hardware;
it stays fully supported on WebRTC).

---

## R-3 — Upstream audio: raw PCM (no on-device Opus encode on the gRPC path)

**Decision**: On the gRPC path, stream **raw 16 kHz s16le PCM** upstream
(`PcmChunk`, 20 ms / 640 B), bypassing the `OpusBridge` encoder the WebRTC path
uses. Downstream, decode per the explicit `AudioChunk.codec`: reuse `OpusBridge`
for `CODEC_OPUS`, passthrough for `CODEC_PCM_S16LE_16K`.

**Rationale**: `audio.proto`'s upstream is `PcmChunk` (raw PCM), matching what
the gateway STT consumes without a resample — so the device does **not** Opus-
encode upstream, a CPU/latency saving versus WebRTC. The existing `AudioBridge`
output is already PCM16 mono, so the mic path feeds the gRPC transport directly.
Downstream codec is explicit in the frame, so the existing `OpusBridge` decoder
is reused only when the gateway sends Opus.

**Alternatives**: Opus upstream over gRPC — rejected (the contract is PCM
upstream; adds needless on-device encode). PCM-only downstream — viable fallback
but wastes LAN bandwidth; honour the gateway's chosen codec instead.

---

## R-4 — Codegen & dependency confinement (POSIX-only grpc++)

**Decision**: Generate C++ stubs from `proto/aivg/satellite/v1/audio.proto` with
`protoc` + `grpc_cpp_plugin` into `sdks/cpp/src/grpc/_generated/` (checked in).
A `cmake/GenerateProto.cmake` regenerates them when `protoc` is present; the
checked-in stubs mean a consumer build needs **no** protoc. Gate the entire gRPC
transport + `grpc++`/`protobuf` link behind `option(AIVG_SAT_ENABLE_GRPC OFF)`,
inside the **POSIX branch only** — the `if(ESP_PLATFORM)` component never
references it (FR-015).

**Rationale**: Mirrors how feature 021 checked in its Python stubs (no toolchain
at install) and how the SDK already gates the voice plane (`AIVG_SAT_ENABLE_VOICE`)
and confines libpeer to the tiers that use it. `grpc++` is acquired via
`find_package(gRPC CONFIG)` / `find_package(Protobuf)` on the POSIX host (RPi OS
ships them; or vcpkg/apt), not vendored.

**Alternatives**: Generate at consumer build — rejected (forces protoc on every
consumer). FetchContent gRPC source build — heavy; deferred to an opt-in for
hosts lacking system gRPC.

---

## R-5 — Transport negotiation in the SDK (align with feature 021 / US3)

**Decision**: Extend the register frame (`proto/messages.build_register`) to
advertise `transport_capabilities` (e.g. `["grpc","webrtc"]` on a gRPC-enabled
RPi build; `["webrtc"]` on ESP32-S3 and WebRTC-only builds). Read the gateway's
`chosen_transport` from the register reply and select the matching `Transport`
at `VoiceSession` begin. A developer MAY pin a transport via `SatelliteOptions`;
an unsatisfiable pin surfaces a `SatError`.

**Rationale**: Feature 021 already implements gateway-side capability
negotiation; the C++ register frame just needs to advertise and honour the
selection. The capability list is derived from build flags (what the binary
actually supports), so it is honest per-tier with no `device_type` branching.

**Alternatives**: Static per-build transport (no negotiation) — rejected (breaks
mixed fleets / the no-flag-day requirement). Always prefer gRPC — rejected
(must fall back to WebRTC against a pre-021 gateway).

---

## R-6 — Reconnect, drop-surfacing, security

**Decision**:
- **Reconnect (FR-012)**: reuse the existing `ControlPlane` reconnect supervisor
  + `Satellite`'s `on_reconnected` re-negotiation hook; for gRPC a dropped
  `Audio.Stream` ends the session and the next turn opens a fresh stream (no
  renegotiation) — the existing `VoiceSessionResult{reason}` event carries it.
- **Drop-surfacing (FR-013)**: map a gRPC stream error to the existing
  `SatError` / `VoiceSessionResult` event the application already handles
  (tone-cue hook) — no new event type.
- **Security (FR-014)**: gRPC channel uses insecure credentials on trusted LAN
  (default), TLS/mTLS for fleet via `grpc::SslCredentials`; never silently
  downgrade a required-auth posture. Matches the gateway's posture (021/R-6).

**Rationale**: The SDK already has reconnect + a session-result event surface;
the gRPC transport plugs into them rather than inventing parallel machinery —
consistent with the seam decision (R-1).

**Alternatives**: gRPC built-in retry on the audio call — rejected ("retry a
voice turn" == "start a new turn"; silent reconnect hides failures the user
should hear, same as the gateway-side reasoning).

---

## R-7 — Testing without hardware

**Decision**: The new `Transport` seam (R-1) enables an in-process
`FakeTransport` that records mic PCM and emits scripted remote audio/events.
`tests/test_transport_seam.cpp` drives a real `VoiceSession` against it to prove
the gRPC-shaped path (PCM up, codec-tagged down, events surfaced) with no
network/hardware. `tests/grpc_audio_smoke.cpp` is the live end-to-end test
against a real gRPC gateway (not a ctest — like the existing `ws_register_smoke`).

**Rationale**: Today there is no transport mock (the map notes tests are pure-
logic or live). The seam refactor is what makes fast, hardware-free transport
tests possible — a direct benefit of R-1. Constitution V's on-hardware proof
(RPi soak; ESP32 spike) remains a separate release gate.

**Alternatives**: Only live tests — rejected (slow, flaky, needs a gateway in
CI). Mock at the gRPC stub layer — heavier and grpc++-coupled; the `Transport`
seam is the cleaner mock boundary.

---

## Resolved unknowns summary

| Unknown | Resolution |
|---|---|
| Is there a transport seam to slot into? | No — introduce abstract `Transport` (R-1) |
| ESP32-S3 gRPC path | Stay on WebRTC; gRPC RPi-first; ESP32 behind a measured spike (R-2) |
| Upstream audio format | Raw PCM 16 kHz; no on-device Opus encode (R-3) |
| Codegen + grpc++ confinement | Checked-in stubs; `AIVG_SAT_ENABLE_GRPC`, POSIX-only (R-4) |
| Transport negotiation | Advertise `transport_capabilities`; honour `chosen_transport` (R-5) |
| Reconnect / drop / security | Reuse existing reconnect + session-result event; insecure-LAN / mTLS (R-6) |
| Hardware-free testing | `FakeTransport` via the new seam (R-7) |
