# Feature Specification: C++ SDK gRPC Transport

**Feature Branch**: `022-cpp-sdk-grpc-transport`  
**Created**: 2026-06-02  
**Status**: Draft  
**Input**: User description: "Add a gRPC bidirectional-streaming transport to the C++ satellite SDK libaivg-sat for native satellites (RPi Zero 2 W / ESP32-S3), consuming the same canonical proto contract as feature 021; phase 1 audio plane alongside the existing WebRTC transport; central constraint decision is the ESP32-S3 tier's gRPC path given PSRAM/binary-size limits"

## Overview

`libaivg-sat` (the C++17 satellite SDK from feature 020) today carries its
device↔gateway audio over **WebRTC** (libpeer) on both supported tiers — RPi
Zero 2 W-class Linux and ESP32-S3. That stack is exactly where the
"stuck connecting" failures live: ICE completes but DTLS/SCTP never finishes, so
wake fires but no audio flows. Feature 021 fixed this on the **gateway** by
adding a **gRPC** transport; the gateway now speaks gRPC, but no native client
does yet.

This feature is the **native-client counterpart**: it adds a gRPC
bidirectional-streaming transport to `libaivg-sat` so a real device gets the
reliable audio plane **end-to-end** — one `Audio.Stream` (mic PCM up;
synthesized audio + transcripts + turn events down), no ICE/DTLS/SCTP to stall.
It consumes the **same canonical contract** as the gateway
(`proto/aivg/satellite/v1/audio.proto`, and `management.proto` for Phase 2), so
the wire cannot drift. The gRPC transport slots in **alongside** the existing
WebRTC transport behind the SDK's transport seam; WebRTC stays available and no
existing WebRTC satellite breaks. Constitution III (generalized to be
transport-neutral in v2.1.0) makes a gRPC voice plane on a native satellite
explicitly constitutional.

**The binding tension** is hardware. The two tiers are not equal:

- **RPi Zero 2 W / Linux** has the headroom to run a full gRPC client. This tier
  is the MVP — it delivers the reliability win on the validation-tier hardware.
- **ESP32-S3 (ESP-IDF, ~4 MB PSRAM)** almost certainly **cannot** fit a full
  gRPC C++ stack (binary size + RAM). Whether — and how — the constrained tier
  gets gRPC is a **research-gated, constraint-driven decision** (Constitution V):
  a minimal HTTP/2 + compact-protobuf client, a lightweight gRPC stack, or the
  ESP32-S3 stays on WebRTC with gRPC scoped to the RPi tier. This spec does
  **not** pre-decide that path; it scopes the constrained tier as a separate,
  evidence-gated deliverable.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - RPi-class native satellite completes a voice turn over gRPC (Priority: P1)

A developer builds a Raspberry Pi Zero 2 W voice satellite with `libaivg-sat`,
configured to use the gRPC transport. The user speaks the wake word and asks a
question; the SDK streams microphone audio to the gateway over a single gRPC
bidirectional stream, and the synthesized reply streams back and plays on the
speaker — reliably, on a plain LAN, with no WebRTC negotiation in the path.

**Why this priority**: This is the end-to-end payoff of feature 021. The gateway
already speaks gRPC; without a native client speaking it too, the reliability
win is unrealized on real hardware. The RPi tier is where full gRPC is feasible,
so it is the minimum shippable slice that proves the whole idea on a device.

**Independent Test**: On an RPi-class build of `libaivg-sat` configured for
gRPC, trigger a wake event and speak; confirm an audible reply plays back and
that the session carried audio both directions over gRPC with no WebRTC
peer-connection setup. Repeatable across gateway restarts and fresh boots
without manual intervention.

**Acceptance Scenarios**:

1. **Given** an RPi-class satellite built with the gRPC transport and adopted by
   a gRPC-capable gateway, **When** the user fires the wake word and speaks,
   **Then** the gateway receives the upstream audio and the satellite plays the
   synthesized reply within the turn.
2. **Given** an active gRPC voice session, **When** the user speaks, **Then**
   streaming transcript text and speaking-started/ended signals arrive on the
   same stream the SDK already surfaces to the application (parity with the
   WebRTC path's events).
3. **Given** a satellite that just completed a turn, **When** the user starts
   another, **Then** a new session is established and completes without a
   multi-second connection-setup delay.
4. **Given** a running satellite, **When** the gateway restarts or the LAN
   blips, **Then** the satellite re-establishes a working voice link on the next
   turn automatically — no manual restart, no boot-order workaround.
5. **Given** a dropped stream mid-turn, **When** it occurs, **Then** the SDK
   surfaces the interruption to the application (a tone-cue hook / event) rather
   than hanging, and the next turn recovers cleanly.

---

### User Story 2 - ESP32-S3 constrained-tier transport decision (Priority: P2)

A developer targets the ESP32-S3 (ESP-IDF, ~4 MB PSRAM). They need to know,
with evidence, whether their device can run the gRPC transport — and if so, in
what form — or whether it stays on WebRTC. The SDK gives a **clear, documented,
measured** answer per tier: the constrained tier either gains a gRPC path that
provably fits the PSRAM/binary budget under the full pipeline, or it is
explicitly kept on WebRTC with the reasons recorded.

**Why this priority**: High-value (the ESP32-S3 is the MVP-lead hardware for the
broader product) but genuinely blocked on research — the path cannot be chosen
responsibly without binary-size and RAM measurements under the full running
pipeline (Constitution V). It is sequenced after the RPi tier proves the design.

**Independent Test**: For the ESP32-S3 tier, produce a build (or a documented
decision with measurements) and verify: either a gRPC-transport firmware image
fits the partition/PSRAM budget and completes a voice turn on-device, **or** a
recorded decision shows the measured cost and keeps the tier on WebRTC. Either
outcome is a pass; an unmeasured guess is a fail.

**Acceptance Scenarios**:

1. **Given** the ESP32-S3 tier, **When** the transport path is decided, **Then**
   the decision cites measured binary size and PSRAM/heap headroom under the
   full pipeline (wake word + capture + transport + playback), not estimates.
2. **Given** the chosen path is an on-device gRPC client, **When** a build is
   produced, **Then** the firmware image fits the device's flash partition and
   the running pipeline stays within its RAM budget, and a voice turn completes.
3. **Given** the chosen path keeps ESP32-S3 on WebRTC, **When** that is decided,
   **Then** the satellite still negotiates correctly (advertises only the
   transports it supports) and the gateway serves it WebRTC without error.

---

### User Story 3 - Transport coexistence & selection in the SDK (Priority: P3)

A developer integrating `libaivg-sat` picks a transport (or lets the device and
gateway negotiate one) via the SDK's existing options surface. WebRTC and gRPC
coexist behind the same transport seam; existing WebRTC integrations keep
working unchanged; the device advertises which transports it supports and the
gateway selects accordingly. There is no flag-day and no breaking API change.

**Why this priority**: Necessary for a real rollout across a mixed fleet but not
required to prove gRPC on one device. It protects existing `libaivg-sat`
integrations and lines the SDK up with the gateway's capability negotiation
(feature 021 / US3).

**Independent Test**: Build the SDK and, for a satellite advertising both
transports, confirm the gateway-selected transport is used; for a WebRTC-only
build, confirm WebRTC is used unchanged; confirm an existing WebRTC integration
compiles and runs with no source change.

**Acceptance Scenarios**:

1. **Given** a satellite built with both transports, **When** it is adopted by a
   gRPC-capable gateway, **Then** it uses gRPC for the voice plane.
2. **Given** a WebRTC-only satellite (or a gateway without gRPC), **When** it is
   adopted, **Then** it uses WebRTC unchanged.
3. **Given** an existing `libaivg-sat` integration written against feature 020,
   **When** this feature lands, **Then** it builds and runs with no required
   source change (the gRPC transport is additive/opt-in).
4. **Given** a developer pins a transport explicitly, **When** the device
   connects, **Then** the SDK honors the pin or surfaces a clear error if the
   gateway cannot satisfy it.

---

### Edge Cases

- **Gateway without gRPC**: a gRPC-capable satellite adopted by a pre-021
  gateway falls back to a mutually-supported transport (WebRTC) or surfaces a
  clear, actionable error — never a silent hang.
- **Stream drop mid-playback / mid-capture**: surfaced to the application
  (tone-cue/event), session ends cleanly, next turn re-establishes.
- **Constrained-tier overflow**: if an ESP32-S3 gRPC build exceeds the flash
  partition or exhausts PSRAM/heap under load, the build/decision fails loudly
  (it does not ship a device that bricks or OOMs mid-turn).
- **Slow device (backpressure)**: a device that can't keep up with downstream
  audio degrades gracefully (no desync, no unbounded buffering) and recovers.
- **Security posture**: trusted-LAN deployments may run unauthenticated;
  fleet deployments use mutual authentication; the SDK MUST NOT silently
  downgrade from a required-auth posture.
- **Toolchain absence**: the SDK build must not require contract-codegen tooling
  on every consumer's machine (generated bindings are provided), and an ESP-IDF
  build must not require a desktop-only dependency.

## Requirements *(mandatory)*

### Functional Requirements

#### Contract & transport seam

- **FR-001**: The SDK MUST speak the **same canonical wire contract** as the
  gateway (`proto/aivg/satellite/v1/audio.proto`; `management.proto` for Phase
  2) — the device and gateway bindings derive from one source so the wire cannot
  drift.
- **FR-002**: The gRPC transport MUST be implemented behind the SDK's existing
  transport seam (the same seam the WebRTC transport uses), so the voice-session
  state machine, reconnect, and application-facing events are reused, not forked.
- **FR-003**: Adding the gRPC transport MUST be **additive**: existing WebRTC
  integrations build and run with no required source change (FR for US3).

#### Audio plane (RPi tier — the MVP)

- **FR-004**: An RPi-class satellite MUST complete a full voice turn over one
  gRPC bidirectional stream: stream microphone audio up, receive synthesized
  reply audio down, and play it back.
- **FR-005**: Upstream microphone audio MUST be delivered in the format the
  gateway's speech pipeline consumes (16 kHz PCM) without an extra device-side
  resample in the common case.
- **FR-006**: Streaming transcripts and turn-lifecycle events (speaking
  started/ended, etc.) MUST be surfaced to the application through the same SDK
  event surface the WebRTC path uses (parity, not a parallel API).
- **FR-007**: A voice session MUST be keyed by the session identifier from the
  management/adoption flow, with no per-session peer-connection negotiation (no
  ICE/DTLS/SCTP) for the gRPC path.

#### Constrained tier (ESP32-S3 — research-gated)

- **FR-008**: The ESP32-S3 transport path MUST be chosen from **measured**
  evidence — binary size and PSRAM/heap headroom under the full running pipeline
  — not estimates (Constitution V).
- **FR-009**: If an on-device gRPC client is chosen for ESP32-S3, the resulting
  firmware MUST fit the device's flash partition and keep the running pipeline
  within its RAM budget, and MUST complete a voice turn on-device before the
  tier is declared supported.
- **FR-010**: If ESP32-S3 stays on WebRTC, the SDK MUST still let that device
  negotiate correctly (advertise only the transports it supports) so the gateway
  serves it WebRTC without special-casing.

#### Negotiation, reliability & security

- **FR-011**: A satellite MUST advertise its supported transports during
  adoption/registration, and use the gateway-selected transport (aligning with
  feature 021's capability negotiation). A developer MAY pin a transport; an
  unsatisfiable pin MUST surface a clear error.
- **FR-012**: After a gateway restart, LAN blip, or boot-order race, a gRPC
  satellite MUST reach a working voice link on the next turn automatically — no
  manual restart, no boot-order/watchdog workaround.
- **FR-013**: When a stream drops mid-turn, the SDK MUST surface the
  interruption to the application (an event/hook the integration can map to a
  tone cue) rather than hang, and the next turn MUST recover cleanly.
- **FR-014**: The transport MUST support an unauthenticated mode for
  trusted-LAN deployments and a mutually-authenticated mode for fleet
  deployments, and MUST NOT silently downgrade from a required-auth posture.
- **FR-015**: The SDK build MUST NOT require contract-codegen tooling on a
  consumer's machine to compile (generated bindings ship with the SDK), and the
  gRPC transport's dependencies MUST be confined to the tiers that use it (an
  ESP32-S3 build that stays on WebRTC must not pull a desktop-only gRPC stack).

#### Management plane (Phase 2 — later)

- **FR-016**: The SDK SHOULD, in a later phase, be able to carry the management/
  control plane (register/adopt, heartbeat, state, control) over the gRPC
  `Management` service so a native satellite needs only one transport — kept as
  a separate concern from the audio plane, sequenced after the audio plane is
  field-proven.

### Key Entities *(include if feature involves data)*

- **Transport (SDK-internal)**: a realization of the device's voice plane —
  WebRTC (existing) or gRPC (new) — selectable behind one seam; carries audio in
  and out and surfaces lifecycle events.
- **Voice session**: one wake-to-reply interaction; keyed by the session id from
  the management/adoption flow; carries the negotiated transport.
- **Transport capability set**: the transports a given build/device supports
  (e.g. `[grpc, webrtc]` on RPi; possibly `[webrtc]` on ESP32-S3), advertised at
  adoption — the basis for gateway selection and developer pinning.
- **Device tier**: the hardware class (RPi Zero 2 W-class Linux; ESP32-S3
  ESP-IDF) whose binding constraints (RAM, flash, PSRAM) determine which
  transports are feasible.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On an RPi-class satellite using the gRPC transport, a spoken
  request after a wake event produces an audible reply on ≥99% of wake events on
  a healthy LAN — eliminating the "wake fires but no audio flows" failure class
  on real hardware.
- **SC-002**: An RPi-class gRPC satellite recovers a working voice link
  automatically within one turn (and under 10 seconds) after a gateway restart
  or transient LAN drop, with zero manual interventions.
- **SC-003**: The delay from end-of-speech to first reply audio on an RPi-class
  device shows no perceptible multi-second connection-setup step versus the
  WebRTC path (the per-session negotiation overhead is gone).
- **SC-004**: An RPi-class gRPC satellite runs a ≥7-day soak under normal use
  with zero manual restarts attributable to the transport.
- **SC-005**: Existing `libaivg-sat` WebRTC integrations build and run after this
  feature with **zero** required source changes (additive transport).
- **SC-006**: The ESP32-S3 transport decision is backed by recorded measurements
  (binary size, PSRAM/heap headroom under the full pipeline); if a gRPC build
  ships for ESP32-S3 it fits the flash partition and completes a voice turn
  on-device; if not, the WebRTC fallback negotiates correctly. (No unmeasured
  decision is acceptable.)
- **SC-007**: A satellite advertising both transports is served gRPC and a
  WebRTC-only satellite is served WebRTC, with no manual per-device transport
  wiring beyond capability advertisement.

## Assumptions

- **RPi-first scope**: Phase 1 / US1 (RPi-class gRPC audio plane) is the
  committed MVP. The ESP32-S3 tier (US2) is **research-gated**: its transport
  path is decided in planning from measured evidence, not pre-decided here. This
  is a deliberate scope boundary, not an omission — flag if ESP32-S3 gRPC must be
  committed in-scope now instead.
- **Contract is fixed**: this feature consumes the feature-021 contract
  (`proto/aivg/satellite/v1/`) verbatim; it introduces **no** gateway or wire
  change. The gateway already speaks gRPC.
- **WebRTC stays**: the existing libpeer WebRTC transport remains for both tiers
  during and after this feature; gRPC is additive and selected by negotiation.
  Retiring WebRTC from native clients is out of scope.
- **Repository placement**: the SDK lives at `sdks/cpp/` in this repo; device
  integration rigs / firmware configs may live in or be consumed by the
  companion `aivg-devices` repo. SDK code and its generated contract bindings
  are owned here.
- **Security default**: trusted-LAN single-home deployments may run
  unauthenticated; fleet deployments use mutual authentication (matching the
  gateway's posture from feature 021).
- **Constitution V gate**: "supported" for either tier means proven end-to-end
  on real hardware (the same voice loop the WebRTC path passes), with the
  constrained tier additionally load-tested with the full pipeline running
  together — not declared from in-vitro builds.

## Dependencies

- Feature 021 (gateway gRPC transport + the canonical `proto/aivg/satellite/v1/`
  contract) — already shipped; this feature is the native-client counterpart.
- Feature 020 (`libaivg-sat` WebRTC SDK) — the SDK and transport seam this
  feature extends.
- The companion `aivg-devices` repo for device integration/firmware rigs used to
  exercise the on-hardware acceptance and soak tests.
