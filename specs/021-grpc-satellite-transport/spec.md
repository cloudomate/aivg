# Feature Specification: gRPC Satellite Transport

**Feature Branch**: `021-grpc-satellite-transport`  
**Created**: 2026-06-02  
**Status**: Draft  
**Input**: User description: "read this 006-grpc-satellite-transport.md i want to implement grpc for audio transport and control, phase 1 move transport and then management"

## Overview

Today native AIVG satellites (Raspberry Pi class, ESP32-S3 class) carry their
device↔gateway **audio plane over WebRTC**. In field bring-up this stack
repeatedly stalls: ICE completes but the DTLS/SCTP handshake never finishes, so
the voice link sits in `connecting` forever — wake fires, the mic arms, but no
audio ever flows and the user hears "no reply." The recovery today is brittle
(container restarts, boot-order guards, watchdog timers) and the failure
re-appears after every gateway restart or network blip.

This feature replaces that audio plane for **native** satellites with a **gRPC
bidirectional streaming transport** — the same primitive Google's Assistant SDK
uses for device↔cloud audio: one connection, two streams (mic up, audio down),
a single schema-checked contract, deadlines and cancellation built in, and a
reconnect that opens a fresh stream instead of renegotiating a peer connection.

The work is **phased**, matching the user's stated sequencing:

- **Phase 1 — Audio/voice transport plane** (this feature's MVP): move the
  real-time audio of a voice turn from WebRTC to gRPC for native satellites.
- **Phase 2 — Management & control plane**: move registration, state, adoption,
  wake/turn events, control messages, and streaming transcripts from the
  existing management WebSocket onto gRPC, so a native satellite needs only one
  transport technology.

**Browser-tab satellites stay on WebRTC** throughout — a browser can't open a
raw HTTP/2 gRPC stream, and WebRTC's NAT-traversal/encryption machinery only
earns its keep in that one case. The two transports therefore **coexist**;
native clients negotiate gRPC, browser clients negotiate WebRTC, and there is no
flag-day cutover.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Native satellite completes a voice turn over gRPC (Priority: P1)

A household has a Raspberry Pi voice satellite adopted by a local AIVG gateway.
The user says the wake word and asks a question. The satellite streams its
microphone audio to the gateway over a gRPC bidirectional stream, the gateway
runs the agent turn, and the synthesized reply streams back over the same
connection and plays on the satellite's speaker — reliably, on a plain LAN, with
no WebRTC ICE/DTLS/SCTP negotiation in the path.

**Why this priority**: This is the entire motivation. Without a reliable audio
plane the product does not work for native deployments. It is the minimum
shippable slice that delivers user value and removes the class of "stuck
connecting" failures that prompted the proposal.

**Independent Test**: On a native satellite configured for the gRPC transport,
trigger a wake event and speak a request; confirm an audible spoken reply plays
back, and that the session established and carried audio both directions without
any WebRTC peer-connection negotiation. Repeatable across gateway restarts and
fresh boots without manual intervention.

**Acceptance Scenarios**:

1. **Given** an adopted native satellite that negotiated the gRPC transport,
   **When** the user fires the wake word and speaks a request, **Then** the
   gateway receives the upstream microphone audio, produces a reply, and the
   satellite plays the synthesized audio back within the turn.
2. **Given** an active gRPC voice session, **When** the user speaks, **Then**
   streaming transcript text and speaking-started/ended signals arrive on the
   same audio connection (no separate out-of-band channel for turn timing).
3. **Given** a native satellite that just completed a turn, **When** the user
   immediately starts another turn, **Then** a new voice session is established
   and completes without a multi-second connection-setup delay.
4. **Given** a running native satellite, **When** the gateway process restarts,
   **Then** the satellite re-establishes a working voice link on the next turn
   automatically, without operator action (no `systemctl restart`, no manual
   power-cycle).
5. **Given** a native satellite booting before the gateway is ready, **When**
   the gateway later becomes available, **Then** the satellite reaches a working
   voice link without boot-order workarounds.

---

### User Story 2 - Management & control plane over gRPC (Priority: P2)

After the audio plane is proven, a native satellite carries **everything** —
registration, adoption, state reporting, wake/turn events, control messages, and
streaming transcripts — over gRPC, so it no longer maintains a separate
management WebSocket. Operators get a single connection technology to reason
about, monitor (with gRPC-native tooling), and secure for a native fleet.

**Why this priority**: High value but explicitly sequenced after Phase 1. The
management WebSocket works adequately today, so this is consolidation rather than
a fix. It removes the cross-channel timing races between the audio plane and the
control plane and lets native satellites drop a whole transport technology.

**Independent Test**: On a native satellite configured for the gRPC transport,
complete the full lifecycle — register, get adopted, report state, fire a
wake/turn, receive control messages — with the management WebSocket disabled,
and confirm every management interaction succeeds over gRPC.

**Acceptance Scenarios**:

1. **Given** a fresh native satellite, **When** it starts up, **Then** it
   registers and can be adopted entirely over gRPC, with no management WebSocket
   connection.
2. **Given** an adopted native satellite, **When** its state changes (online,
   pending, factory reset), **Then** the gateway reflects the new state, sourced
   from the gRPC control plane.
3. **Given** an operator sending a control message (e.g., re-adopt, restart a
   session, push config), **When** it is issued, **Then** the native satellite
   receives and acts on it over gRPC.
4. **Given** a native satellite migrated to the gRPC management plane, **When**
   it is inspected with standard gRPC tooling, **Then** the management surface is
   introspectable without bespoke debugging.

---

### User Story 3 - Transport coexistence and safe migration (Priority: P3)

The AIVG gateway serves a mixed fleet: browser-tab satellites, legacy native
satellites still on WebRTC, and new native satellites on gRPC. Each satellite
advertises what transports it supports; the gateway selects the best mutually
supported transport. Operators can pin a satellite's transport explicitly for a
bench or a rollout. No existing satellite breaks when the gRPC transport is
introduced, and there is no flag-day where every device must switch at once.

**Why this priority**: Necessary for a real-world rollout but not required to
prove the core idea on a single device. It protects the existing fleet and the
browser use case while Phase 1 and Phase 2 land incrementally.

**Independent Test**: Stand up a gateway and connect (a) a browser satellite,
(b) a native satellite advertising only WebRTC, and (c) a native satellite
advertising gRPC + WebRTC; confirm each negotiates the expected transport and
completes a voice turn, with no manual per-device wiring beyond capability
advertisement.

**Acceptance Scenarios**:

1. **Given** a satellite that advertises both gRPC and WebRTC, **When** it is
   adopted, **Then** the gateway selects gRPC.
2. **Given** a browser-tab satellite (WebRTC only), **When** it is adopted,
   **Then** the gateway selects WebRTC and the satellite works unchanged.
3. **Given** a legacy native satellite advertising only WebRTC, **When** the
   gRPC transport is enabled gateway-wide, **Then** the legacy satellite keeps
   working over WebRTC with no change required.
4. **Given** an operator pinning a satellite to a specific transport, **When**
   that satellite connects, **Then** the gateway honors the pin (or surfaces a
   clear error if the satellite cannot satisfy it).

---

### Edge Cases

- **Disconnect mid-turn**: If the audio stream drops while the user is speaking
  or while the reply is playing, the satellite surfaces the interruption to the
  user (e.g., an audible tone cue) rather than silently freezing, and the next
  turn re-establishes cleanly.
- **Slow consumer / backpressure**: If a satellite cannot keep up with the
  downstream audio rate, the system degrades gracefully (no desync, no unbounded
  buffering, no crash) and recovers when the device catches up.
- **Gateway restart during an active session**: The in-flight session ends
  cleanly and the next wake establishes a new session automatically.
- **Network blip**: A transient LAN drop does not require a manual restart;
  recovery is automatic on the next turn.
- **Capability mismatch**: A satellite that advertises gRPC connecting to a
  gateway with the gRPC transport disabled (or vice-versa) falls back to a
  mutually-supported transport, or surfaces a clear, actionable error if none
  exists.
- **Wake event timing**: The session start is signalled explicitly from the
  client (an explicit wake event on the stream) rather than inferred from audio
  energy, so the gateway is precise about when a turn begins.
- **Security posture mismatch**: A satellite expecting an encrypted (mutually
  authenticated) link must not silently fall back to an unauthenticated one when
  the deployment requires authentication.

## Requirements *(mandatory)*

### Functional Requirements

#### Contract & schema

- **FR-001**: The system MUST define a single canonical wire schema for the
  satellite audio plane that is the one source of truth for both the gateway and
  every native satellite client, such that the gateway and client contracts
  cannot drift independently.
- **FR-002**: The audio schema MUST carry, upstream (device→gateway):
  microphone audio frames, client lifecycle events (at minimum wake-fired,
  end-of-utterance, barge-in start), and a session header that identifies the
  voice session and the client's codec preferences.
- **FR-003**: The audio schema MUST carry, downstream (gateway→device):
  synthesized audio frames with an identified codec, server lifecycle events (at
  minimum speaking-started, speaking-ended, voice-activity-detected), and
  streaming transcript text (partial and final) on the same connection.
- **FR-004**: The schema MUST be versioned and evolvable such that additive
  changes (new fields, new event kinds) do not break existing clients.

#### Phase 1 — Audio transport plane

- **FR-005**: The gateway MUST accept a gRPC bidirectional audio stream from a
  native satellite and run a complete voice turn over it: receive upstream
  microphone audio, drive the agent turn, and stream synthesized reply audio
  back on the same stream.
- **FR-006**: A voice session MUST be keyed by a session identifier that
  originates from the management/adoption flow, so the audio stream is
  unambiguously tied to the correct satellite and turn.
- **FR-007**: The system MUST open one audio stream per voice session — opened
  when a session begins and closed when it ends — without requiring any
  per-session peer-connection negotiation (no ICE/DTLS/SCTP handshake) for
  native satellites.
- **FR-008**: Upstream microphone audio MUST be delivered in a format the
  gateway's speech pipeline consumes without an extra resampling step in the
  common case.
- **FR-009**: The gateway MUST choose the downstream audio codec and the
  satellite MUST be able to render it; the negotiated/chosen codec MUST be
  explicit in the stream rather than assumed.
- **FR-010**: Streaming transcripts and turn-timing events MUST travel on the
  audio stream itself, eliminating cross-channel timing races between audio and
  control.

#### Phase 2 — Management & control plane

- **FR-011**: The system MUST allow a native satellite to perform its full
  management lifecycle — registration, adoption, state reporting, and receiving
  control messages — over gRPC, without a separate management WebSocket.
- **FR-012**: Wake/turn lifecycle events MUST be expressible over the gRPC
  control plane with explicit, precise session-start semantics (not inferred
  from audio energy).
- **FR-013**: The management surface over gRPC MUST be introspectable with
  standard gRPC tooling (service reflection / schema-driven inspection).
- **FR-014**: Migrating a native satellite to the gRPC management plane MUST NOT
  change the observable management semantics that operators and the existing CLI
  rely on (the same lifecycle states and control actions remain available).

#### Coexistence, negotiation & migration

- **FR-015**: A satellite MUST advertise its supported transports during the
  existing adoption/registration flow, and the gateway MUST select the best
  mutually-supported transport (preferring gRPC for native, WebRTC for browser).
- **FR-016**: The gateway MUST continue to serve WebRTC for browser-tab
  satellites unchanged, and MUST continue to serve existing WebRTC native
  satellites without requiring them to migrate.
- **FR-017**: Operators MUST be able to pin or override a satellite's transport
  (e.g., for a bench or staged rollout), and the system MUST surface a clear
  error when a pin cannot be satisfied.
- **FR-018**: Introducing the gRPC transport MUST NOT require a simultaneous
  fleet-wide cutover; native satellites migrate incrementally.

#### Reliability, security & operability

- **FR-019**: After a gateway restart, network blip, or boot-order race, a
  native satellite on the gRPC transport MUST reach a working voice link on the
  next turn automatically, without operator intervention or the WebRTC-era
  workarounds (boot-order guards, watchdog timers, manual restarts).
- **FR-020**: When an audio session drops mid-turn, the satellite MUST surface
  the interruption to the user (e.g., a tone cue) rather than freeze silently,
  and the next turn MUST recover cleanly.
- **FR-021**: The system MUST handle a slow downstream consumer without audio
  desync, unbounded buffering, or crash, and recover when the device catches up.
- **FR-022**: The transport MUST support an unauthenticated mode for trusted-LAN
  deployments and a mutually-authenticated encrypted mode for fleet deployments,
  and MUST NOT silently downgrade from an authenticated posture when the
  deployment requires authentication.
- **FR-023**: Stuck/failed voice links MUST be diagnosable at a single layer
  (clear, actionable signal of why a link is not carrying audio) rather than
  requiring multi-layer investigation across ICE/DTLS/SCTP state machines.

### Key Entities *(include if feature involves data)*

- **Voice session**: A single wake-to-reply (or multi-turn) interaction between
  one satellite and the gateway. Identified by a session id that ties together
  the management/adoption context and the audio stream; carries the negotiated
  transport and downstream codec.
- **Transport capability set**: The list of transports a satellite supports
  (e.g., gRPC, WebRTC), advertised at adoption time; the basis for gateway
  transport selection and for operator pinning.
- **Audio frame**: A unit of real-time audio — upstream microphone audio
  (device→gateway) or downstream synthesized audio (gateway→device) — with
  timing/sequence and, downstream, an explicit codec.
- **Lifecycle event**: A discrete signal on the stream — client-side
  (wake-fired, end-of-utterance, barge-in) or server-side (speaking-started,
  speaking-ended, voice-activity-detected).
- **Transcript**: Streaming recognized text for a turn, partial or final,
  delivered on the audio stream.
- **Management/control message**: Registration, adoption, state, and operator
  control actions; on the WebSocket today, on gRPC for native satellites after
  Phase 2.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a native satellite using the new transport, a spoken request
  after a wake event produces an audible reply on at least 99% of wake events on
  a healthy LAN — eliminating the "wake fires but no audio ever flows" failure
  class.
- **SC-002**: A native satellite recovers a working voice link automatically
  within one turn (and under 10 seconds) after a gateway restart or transient
  network drop, with zero manual interventions (no restarts, no power-cycles).
- **SC-003**: The delay between the user finishing speaking and the first audio
  of the reply is reduced versus the WebRTC path by removing the per-session
  connection-setup overhead (target: no perceptible multi-second connection
  setup before audio begins; first reply audio starts within a small fraction of
  a second of the gateway producing it).
- **SC-004**: A native satellite runs a multi-day soak (≥7 days of normal use)
  with zero manual restarts attributable to a stuck/failed transport.
- **SC-005**: Across the gateway's mixed fleet, browser-tab satellites and
  legacy WebRTC native satellites continue to complete voice turns with no
  regression after the gRPC transport is enabled (0 broken existing satellites).
- **SC-006**: A satellite advertising both transports is served gRPC, and a
  browser satellite is served WebRTC, with no per-device manual transport wiring
  beyond capability advertisement, in 100% of adoptions.
- **SC-007**: When a voice link is not carrying audio, an operator can identify
  the cause from a single, clear signal rather than inspecting multiple
  connection-layer state machines — measured by removing the WebRTC-era
  boot-order guards, watchdog timers, and manual-restart runbook steps for
  native gRPC satellites.
- **SC-008**: After Phase 2, a native satellite completes its full management
  lifecycle (register → adopt → report state → receive control) with the
  management WebSocket disabled, demonstrating single-transport operation.

## Assumptions

- **Repository split**: This feature owns the gateway/server side and the shared
  canonical wire contract within `aivg` (aivg-core). The native C++ client
  implementation (rpi-pipewire, xvf3800-esp32s3, future hardware) lives in the
  companion `aivg-devices` repository and consumes the same canonical contract;
  client work is coordinated but tracked there.
- **Phase ordering**: Phase 1 (audio plane) is the committed MVP and ships
  first; Phase 2 (management/control plane) is in scope for this feature but
  sequenced after Phase 1 is proven in the field. Each phase is independently
  shippable.
- **Browser satellites remain on WebRTC** indefinitely; gRPC targets native
  satellites only. gRPC-Web + proxy for browsers is explicitly out of scope.
- **No flag-day**: WebRTC and gRPC coexist on the gateway during and after
  migration; native satellites move incrementally.
- **Wire-contract impact**: This is a new transport with its own schema; the
  existing REST/WebSocket management contract and the WebRTC path are unchanged
  for clients that keep using them. Whether the AIVG contract version bumps and
  by how much is a planning-phase decision, not assumed here.
- **Security default**: Trusted-LAN deployments may run the transport
  unauthenticated; fleet deployments use mutual authentication. The default for
  a local single-home deployment is the trusted-LAN posture.
- **Upstream audio format**: Upstream microphone audio uses a format the
  gateway's speech pipeline already consumes without resampling in the common
  case; the gateway selects the downstream codec and may transcode once.
- **Downstream relationship**: Retiring WebRTC from native clients entirely is a
  later, gradual step beyond this feature; this feature delivers coexistence and
  the native-gRPC path, not the removal of WebRTC.
- **Existing dependency**: The gateway runtime already includes the libraries
  needed to host a gRPC service in its current dependency tree (no new
  agent-platform plugin coupling is introduced — Constitution Principle IV).

## Dependencies

- The existing satellite adoption/registration flow (to advertise transport
  capabilities and mint the session identifier that keys the audio stream).
- The existing gateway voice pipeline (speech-to-text, agent turn, text-to-
  speech) that the new transport feeds and drains.
- The companion `aivg-devices` repository for the native client implementation
  that consumes the canonical contract.
