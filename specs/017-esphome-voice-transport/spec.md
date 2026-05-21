# Feature Specification: ESPHome Voice Assistant transport

**Feature Branch**: `017-esphome-voice-transport`
**Created**: 2026-05-20
**Status**: Draft
**Input**: User description: "ship the ESPHome native API transport on the AIVG gateway so any existing ESPHome voice satellite (Home Assistant Voice Preview Edition, M5Stack Atom Echo, custom ESP32 firmware) talks to AIVG with no client-side code from us — then ship 016 (libaivg-sat C++ SDK) afterwards as a clean Tier-A-only Linux/macOS/RPi binding"

## Clarifications

### Session 2026-05-20

- Q: Proto schema sourcing — vendor `.proto` files, depend on `aioesphomeapi`, or hand-roll a serializer? → A: **`aioesphomeapi`** (depend on the upstream Python library; reuse its `api_pb2` proto-generated types + framing helpers, mirroring how OHF-Voice's `linux-voice-assistant` imports from it).
- Q: Concurrency model — one `asyncio.Task` per connected device, or a single pooled connection loop? → A: **One task per device** (anchored to the existing event loop; matches the aiortc-session pattern; simpler per-device cleanup).
- Q: Session-object scope — reuse `aivg_core.webrtc.session.Session` parameterized over the existing `MediaTransport` Protocol, extract a transport-neutral base class, or build a parallel `EsphomeSession`? → A: **Reuse `webrtc.Session` verbatim** (the ESPHome connection provides a `MediaTransport`-conforming adapter that pumps PCM frames in/out; no `Session` class changes).

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A Home Assistant Voice Preview Edition box runs against AIVG without Home Assistant (Priority: P1) 🎯 MVP

A maker / homelab user owns the Home Assistant Voice Preview Edition
hardware (or any ESP32-based ESPHome voice satellite — M5Stack Atom
Echo, ESPHome's reference designs, custom firmware they wrote). They
already have the device flashed with the standard ESPHome voice
satellite firmware. They want to point it at AIVG instead of Home
Assistant — same hardware, same firmware, **different brain**: a
real conversational agent (Hermes today, OpenClaw or others
tomorrow) instead of HA Assist's intent matcher.

They write the AIVG gateway's IP into the device's ESPHome config
(or use the same secrets / API key they'd give Home Assistant), the
device connects to AIVG's new TCP server, the user holds the device's
wake-word / push-to-talk trigger, speaks, releases — and one full
voice turn (mic → STT → agent → TTS → speaker) completes through
the same `AgentPlatform` plugin that the WebRTC clients route
through.

**Why this priority**: this is the entire feature. AIVG's
microcontroller story (originally planned as feature 016 Tier B)
ships in one shot here by reusing the existing ESPHome firmware
ecosystem — we don't write client-side embedded code, we add one
new transport handler to the gateway. The cost-of-entry for an AIVG
user collapses from "build custom firmware" to "buy a $30 box and
edit one config line."

**Independent Test**: a Home Assistant Voice Preview Edition device
(or equivalent ESPHome voice satellite) configured with the AIVG
gateway's address completes one voice turn end-to-end against a
Hermes-backed AIVG host. The gateway log shows the same
`session opened → transcribed → turn complete` shape that WebRTC
sessions produce — proving the transport is plumbed through the
same `AgentPlatform` verbs.

**Acceptance Scenarios**:

1. **Given** an ESPHome voice satellite device flashed with the upstream voice-assistant firmware and configured with the AIVG gateway's TCP endpoint and API key, **When** the device boots, **Then** it appears in AIVG's `/devices` list (REST + management WS) within 5 seconds and shows `state: idle`.
2. **Given** an ESPHome voice satellite already adopted, **When** the user triggers a turn (wake-word, hardware button, or any device-side speech-start event), **Then** the gateway routes the inbound audio through `AgentPlatform.transcribe → agent_step → synthesize` exactly as it does for WebRTC sessions today, and the reply audio reaches the device's speaker.
3. **Given** a Hermes-backed gateway with feature-008 streaming enabled, **When** an ESPHome device finishes a voice turn, **Then** the spoken reply arrives sub-sentence-streamed (the platform's `agent_stream` extension fires for ESPHome transports too — the transport choice doesn't disable streaming).

---

### User Story 2 — The wire-protocol cost is bounded: existing WebRTC clients keep working unchanged (Priority: P1)

The TypeScript SDK (`@aivg/sat-sdk` 0.1.3) and the electron-test
client continue to drive voice turns against the same gateway with
zero code changes. The contract version advances from `1.0.0` to
`1.1.0` (additive — new transport added, old transport unchanged),
not a major bump. WebRTC clients see the management plane as
identical to today.

**Why this priority**: feature 014 shipped a TypeScript SDK against
the frozen `1.0.0` surface, and feature 015 made the constitutional
case that the wire is locked. This feature loosens that lock
**only** in the additive direction (one new transport server bound
to one new TCP port, no changes to existing WS/REST/WebRTC paths).
Breaking 014 / 015's clients is a non-starter.

**Independent Test**: the electron-test smoke (feature 014 / SC-002)
passes byte-for-byte against the post-017 gateway with the same
`@aivg/sat-sdk 0.1.3` binary — no rebuild, no config flip. The
gateway's `aivg --contract-version` outputs `1.1.0` (was `1.0.0`)
and the SDK's compatibility check accepts the bump on a
same-major-version basis.

**Acceptance Scenarios**:

1. **Given** the unchanged `@aivg/sat-sdk 0.1.3` electron-test client, **When** the user PTTs against the post-017 gateway, **Then** the full STT → agent → TTS cycle completes identically to pre-017 behaviour.
2. **Given** the gateway's `aivg --contract-version` envelope, **When** any client reads it, **Then** the value is `1.1.0` and the embedded transport list explicitly enumerates `["webrtc", "esphome_api"]` (or equivalent — final names in the contract).

---

### User Story 3 — One AgentPlatform, two transports — constitutional Principle IV preserved (Priority: P1)

The Hermes (and future OpenClaw) plugin is **unchanged**. A voice
session arriving over ESPHome's TCP transport reaches the platform
through the same `transcribe → agent_step → synthesize → endpoint`
verbs that a WebRTC session does. The plugin author never knows
which transport carried the session; the runtime closure from
feature 015 holds.

**Why this priority**: this is the design-time bet. If a new
transport required plugin changes, every future platform plugin
would need a transport-matrix worth of code paths — the opposite of
Principle IV. The whole point of feature 015 was to make THIS
feature a transport-only addition.

**Independent Test**: a contract test under
`tests/contract/test_esphome_transport.py` constructs an ESPHome
session against the echo platform fixture (NOT Hermes) and drives
one turn end-to-end. The echo platform's `agent_step` deltas
accumulate, `synthesize` is called, and the audio reaches the
fake-ESPHome client — without the Hermes plugin module ever being
imported.

**Acceptance Scenarios**:

1. **Given** the echo `AgentPlatform` fixture loaded as the active plugin, **When** an ESPHome-protocol client opens a session and sends an utterance, **Then** the echo's canned reply is synthesized and returned to the client identically to how it would be over WebRTC.
2. **Given** the Hermes plugin loaded as the active platform, **When** an ESPHome session and a WebRTC session run concurrently against the same gateway, **Then** both sessions complete their turns successfully without interfering with each other's `AgentPlatform` state.

---

### User Story 4 — Multi-device: one gateway serves many ESPHome satellites concurrently (Priority: P2)

A small homelab or office deploys 3-12 ESPHome voice satellites
around different rooms — kitchen, living room, study, garage. They
all point at the same AIVG gateway. The gateway routes each
device's turns independently, keeping per-device conversation
state, without one device's turn blocking another's.

**Why this priority**: the use case AIVG ultimately targets is
multi-room voice. A single-device-only architecture would be a
non-starter for the maker / homelab story.

**Independent Test**: 4 simulated ESPHome clients (test fixtures
implementing the proto wire) connect to the gateway concurrently,
each runs one voice turn against the echo platform, and all four
complete within the same wall-clock budget as a single turn (within
a small concurrency-overhead factor). Mirror of feature-015
`test_sc005_ten_plus_concurrent_sessions`.

**Acceptance Scenarios**:

1. **Given** N (3 ≤ N ≤ 12) ESPHome-protocol clients connected simultaneously, **When** each triggers a turn independently, **Then** the gateway processes them concurrently and emits a per-device `turn complete` log line for each.
2. **Given** a session arriving over ESPHome and another arriving over WebRTC at the same instant, **When** both are routed through the same `AgentPlatform`, **Then** the plugin's per-session state remains independent (no cross-talk between transports).

---

### User Story 5 — The management-plane device list shows ESPHome devices alongside WebRTC ones (Priority: P3)

The existing AIVG management plane (`/devices`, `/devices/{id}/state`,
the `aivg list` CLI, the management-plane WS) shows ESPHome devices
in the same list as WebRTC devices, with a `transport: "esphome_api"`
discriminator. The operator's mental model is "one gateway, N
devices" — not "one gateway, two device lists by transport."

**Why this priority**: nice-to-have for v1. The minimal path
(ESPHome devices appear in the list, transport tagged) is small.
Per-transport-specific config (e.g., "show me only ESPHome
devices") is a v1.1 polish.

**Acceptance Scenarios**:

1. **Given** a mix of ESPHome and WebRTC devices adopted, **When** the operator runs `aivg list`, **Then** all devices appear with a `transport` field showing which transport they registered through.
2. **Given** a management-plane WS subscriber, **When** an ESPHome device's state changes, **Then** the subscriber receives the same `state_update` message shape they receive for WebRTC devices — only the `transport` field differs.

---

### Edge Cases

- **ESPHome device sends an audio frame before adoption confirms**: gateway MUST buffer (small bounded queue, ≤ 1 second) until adoption completes, then drain; if adoption fails the buffer is discarded with a logged warning.
- **ESPHome device disconnects mid-turn**: gateway MUST cancel the in-flight `AgentPlatform.agent_step` / `agent_stream` for that session, free resources promptly, and emit a `session_ended reason="transport_dropped"` log line.
- **API key mismatch on initial handshake**: gateway MUST refuse the connection with a typed protocol error and log the attempt; the device retries via its normal reconnect path.
- **ESPHome protocol-version skew** (the device speaks a future ESPHome version with new message types): unknown messages MUST be ignored (logged at DEBUG); the gateway MUST NOT crash on unknown opcodes.
- **Two devices try to register with the same device ID**: gateway MUST treat the new connection as a replacement (drop the old socket, accept the new), matching how the WebRTC management plane handles the same race today.
- **ESPHome audio frame at a sample rate the active `AgentPlatform` doesn't support**: gateway MUST resample server-side (existing WebRTC path already does this for the 16 kHz / 48 kHz mismatch) — the resampling code is shared, not transport-specific.
- **Wake-word fires on the device but the user never speaks**: gateway's existing silence-detector (the platform's `endpoint(frame)` verb) closes the turn cleanly; no transport-specific timeout needed.
- **Gateway crash / restart while ESPHome devices are connected**: devices' upstream firmware already implements reconnect-with-backoff; the gateway just needs to accept the reconnect cleanly. No new state-replay logic.

## Requirements *(mandatory)*

### Functional Requirements

#### New server-side transport

- **FR-001**: The AIVG gateway MUST listen on a configurable TCP port (default `6053` — ESPHome's well-known API port) and speak the ESPHome native API protocol (varint-prefixed protobuf framing, message types from the ESPHome `.proto` schemas). The proto-generated message types and framing helpers MUST be sourced from the upstream `aioesphomeapi` Python library (depended on via PyPI, pinned to a known-good version range). Vendoring `.proto` files or hand-rolling a serializer is explicitly REJECTED — `aioesphomeapi.api_pb2` + `aioesphomeapi.core` are the canonical sources of truth, matching how OHF-Voice's `linux-voice-assistant` imports them.
- **FR-002**: The new transport MUST be **additive** — a new aiohttp/asyncio listener bound to a new port, NOT a modification of the existing management-plane (`8643`) or voice-plane (`8644`) ports. Disabling the transport via config MUST leave the existing planes byte-for-byte identical to pre-017 behaviour.
- **FR-003**: A satellite config flag MUST gate the transport: `transports.esphome_api.enabled` (default: `false` — opt-in for v1 so existing deployments don't open a new port without the operator's consent). The config schema MUST extend the existing `~/.satellite/config.yaml` without breaking the existing parser.

#### Wire-protocol fidelity

- **FR-004**: The transport MUST implement the **subset** of the ESPHome native API needed for the voice-satellite use case: `HelloRequest/Response`, `ConnectRequest/Response`, `AuthenticationRequest/Response`, `PingRequest/Response`, `DisconnectRequest/Response`, `DeviceInfoRequest/Response`, `ListEntitiesRequest`, plus the `voice_assistant_*` message family (audio in, audio out, event states, configuration).
- **FR-005**: The transport MUST be wire-compatible with the upstream ESPHome voice-assistant firmware at a level sufficient for the Home Assistant Voice Preview Edition device and any device built from ESPHome's reference voice satellite YAML to work unmodified against AIVG.
- **FR-006**: When the ESPHome device sends device-side wake-word events (`VoiceAssistantWakeStart` / equivalent), the gateway MUST honour them as the equivalent of a voice session opening; the gateway does **not** run its own wake-word.

#### AgentPlatform plumbing (constitutional Principle IV)

- **FR-007**: An inbound ESPHome session MUST be routed through the same `AgentPlatform` verbs (`transcribe`, `agent_step`, `synthesize`, `endpoint`) as a WebRTC session. The plugin author MUST NOT need to know which transport carried a session.
- **FR-008**: The transport-specific code MUST live entirely under a new module (e.g., `src/aivg_core/transports/esphome/`) and MUST NOT modify `aivg_core/platforms/`, `aivg_core/adapter.py`, or any plugin-internal file. The only modification outside the new module is one new wiring line in `aivg_core/adapter.py` to start the new server alongside the existing two.
- **FR-009**: The transport MUST reuse `aivg_core.webrtc.session.Session` **verbatim** (no class refactor, no parallel class). The ESPHome connection MUST adapt itself to the existing `MediaTransport` Protocol (`receive() → Optional[bytes]`, `send_audio(bytes)`, `stop_playback()`, `connection_state`, `close()`) so the per-turn state machine is shared across transports by composition, not inheritance. If a leak in the `MediaTransport` abstraction is discovered during implementation, the resolution is a minimal patch to that Protocol — NOT a refactor of `Session`.

#### Authentication & device adoption

- **FR-010**: The transport MUST support ESPHome's plaintext-API-key authentication mode for v1 (the simpler of ESPHome's two auth modes). The encrypted-Noise-protocol mode is OUT of scope for v1 (deferred to v1.1).
- **FR-011**: API keys MUST be configured per-device through the existing AIVG management plane (`/devices/register` or a new admin endpoint — implementation choice in /speckit-plan). The keys MUST NOT be hardcoded in source.
- **FR-012**: An ESPHome device that successfully authenticates MUST appear in the existing AIVG device registry (the same `aivg_core.registry.Registry` instance the WebRTC path uses), with a `transport: "esphome_api"` discriminator on the device record.

#### Management plane integration

- **FR-013**: `aivg list` MUST show ESPHome devices alongside WebRTC devices. The output format extends the existing schema with a `transport` field — no breaking schema changes.
- **FR-014**: The management-plane WS broadcasts (state updates, adoption events, log entries) MUST fire for ESPHome devices using the same message types and shapes as WebRTC devices, with the transport discriminator added.
- **FR-015**: ESPHome-device-specific log entries MUST flow through the existing `LogSink` (`~/.hermes/logs/gateway.log` on Hermes hosts) with the standard JSON envelope and a `source: "esphome"` discriminator (or an additional `transport: "esphome_api"` field — naming finalized in /speckit-plan).

#### Contract versioning

- **FR-016**: The gateway's `aivg --contract-version` envelope MUST advance from `1.0.0` to `1.1.0` (semver MINOR — additive change). The envelope MUST also include an enumerated `transports: [...]` list so newer clients can discover which transports the gateway speaks.
- **FR-017**: The existing TypeScript SDK (`@aivg/sat-sdk` 0.1.3) MUST continue to work against the post-017 gateway with no rebuild — its compatibility check is same-major; minor bumps pass.

#### Concurrency

- **FR-021**: The transport MUST run **one `asyncio.Task` per connected device**, anchored to the gateway's existing event loop. The task owns the device's TCP socket, its protobuf framing state, and its reference to the per-session `Session` instance. Task cancellation MUST clean up the socket, the session, and any pending platform work within the existing barge-in deadline (300 ms). A pooled-loop / single-task multiplexer is explicitly REJECTED.

#### Quality gates (binding regression boundaries)

- **FR-018**: A new test under `tests/integration/test_esphome_transport_basic.py` MUST drive one voice turn through the new transport against the echo platform fixture. NO Hermes import in the test (mirrors feature-015 platform-agnostic test pattern).
- **FR-019**: The existing 290-test suite MUST continue to pass. No semantic change to any existing test.
- **FR-020**: A live smoke against a real ESPHome voice satellite (Home Assistant Voice PE, or equivalent) MUST complete one voice turn end-to-end against the AIVG gateway. The smoke procedure is documented in the feature's `quickstart.md`.

#### Out of scope (v1)

- **OOS-001**: ESPHome's encrypted Noise-protocol API mode. Plaintext API-key auth in v1; encryption a v1.1 follow-up.
- **OOS-002**: Wake-word detection on the gateway side. We rely on the device's existing wake-word (microWakeWord, OpenWakeWord). The gateway runs no wake-word model.
- **OOS-003**: mDNS / Zeroconf service discovery on the gateway side. Devices find the gateway by configured hostname/IP, mirroring how ESPHome devices find Home Assistant today.
- **OOS-004**: Custom ESPHome firmware — we ship NO embedded code in this feature. The point of 017 is that existing ESPHome firmware works as-is.
- **OOS-005**: Changes to the WebRTC transport or the TypeScript SDK. They are stable at feature 014 / 015's surface.
- **OOS-006**: Implementing Home Assistant's full ESPHome API surface (entity exposure, device-state polling, OTA push, sensor reads). We implement ONLY the subset needed for the voice-satellite role.
- **OOS-007**: The C++ SDK (libaivg-sat). That's feature 016, which now becomes Tier-A-only (Linux/macOS/RPi) and ships AFTER this feature.

### Key Entities

- **`EsphomeTransport`** — the new server, a long-lived `asyncio.start_server` listener bound to the configured TCP port. Owns the listener socket; accepts incoming connections, spawns one `asyncio.Task` per device running an `EsphomeConnection` co-routine.
- **`EsphomeConnection`** — one per connected device (one `asyncio.Task` each — FR-021). Owns the device's TCP socket, the protobuf framing state (consuming `aioesphomeapi.core` helpers), the device's auth state, and a reference to the per-session `Session` instance that routes audio through `AgentPlatform`.
- **`EsphomeMediaTransport`** — a thin adapter satisfying the existing `aivg_core.webrtc.session.MediaTransport` Protocol, backed by the `EsphomeConnection`'s inbound/outbound PCM queues. This is the seam that lets `Session` work verbatim across transports (FR-009).
- **Proto message types** — re-exported from `aioesphomeapi.api_pb2` (HelloRequest, ConnectRequest, AuthenticationRequest, PingRequest, DisconnectRequest, DeviceInfoRequest, ListEntitiesRequest, and the `voice_assistant_*` family). NOT vendored; consumed via PyPI dep.
- **`Session`** — REUSED VERBATIM from `aivg_core/webrtc/session.py`. No class refactor; the transport adapts to `MediaTransport` (FR-009).

### Assumptions

- The `aioesphomeapi` PyPI package (MIT-licensed) re-exports the proto-generated message types and framing helpers AIVG needs. Adding it as a runtime dependency is acceptable per AIVG's existing dep policy (already pulling in `aiortc`, `aiohttp`, `httpx`, etc.). If a future ESPHome protocol bump requires schema features `aioesphomeapi` does not yet expose, the fallback is a minor PR to `aioesphomeapi` upstream — NOT vendoring schemas locally.
- "ESPHome voice satellite firmware" means the upstream voice-assistant YAML preset shipped in ESPHome's official examples (or any drop-in-compatible derivative). Firmware authored against a divergent fork is not in scope.
- The Home Assistant Voice Preview Edition hardware ships with the upstream firmware preset by default, so it is the **reference device** for the live smoke (FR-020).
- AIVG's existing `aivg_core.registry.Registry` and `aivg_core.management.service.ManagementService` are already transport-agnostic enough to handle a new device class with a `transport` discriminator. If they are not, the refactor that makes them so is part of this feature.
- The feature-015 `AgentPlatform` runtime closure is the binding seam — feature 017 adds a NEW caller of those verbs without touching the verbs themselves. No plugin (Hermes, OpenClaw, echo) needs modification.
- The TypeScript SDK (`@aivg/sat-sdk`) is unchanged. It already accepts minor-version bumps on the contract.

### Dependencies

- **Hard dependencies on prior features**:
  - Feature 011: contract version 1.0.0 surface (this feature additively bumps to 1.1.0).
  - Feature 014: `@aivg/sat-sdk` 0.1.3 is the consumer that MUST keep working untouched.
  - Feature 015: the `AgentPlatform` Protocol is the **only** way the new transport reaches the agent. Feature 015's runtime closure makes 017 a one-listener addition rather than a plugin-touching change.
- **External dependencies**:
  - **`aioesphomeapi`** (PyPI, MIT) — supplies the proto-generated message types (`aioesphomeapi.api_pb2`), the varint framing helpers (`aioesphomeapi.core`), and tracks ESPHome protocol updates upstream. Pinned to a version range in /speckit-plan. This locks Q1.
  - `protobuf` (transitively via `aioesphomeapi`).
  - Reference reading for the server role this feature is building: OHF-Voice's `linux-voice-assistant` repo (Apache-2 / open-source), which imports from `aioesphomeapi.api_pb2` and `aioesphomeapi.core` in exactly this configuration.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A Home Assistant Voice Preview Edition device (or equivalent ESPHome voice satellite) completes one full voice turn against the AIVG gateway in under 30 seconds wall-clock, with no client-side code change. Measured by live host smoke.
- **SC-002**: The contract version advances from `1.0.0` to `1.1.0`. The TypeScript SDK 0.1.3 (electron-test) continues to drive voice turns against the post-017 gateway with **zero** rebuild and identical observable behaviour. Measured by re-running the feature-014 electron-test smoke against the post-017 gateway.
- **SC-003**: ZERO Hermes-plugin (or any other agent-platform plugin) source files are modified by this feature. Constitution Principle IV remains a one-line guarantee. Measured by `git diff main -- src/aivg_core/platforms/` returning zero lines for this feature.
- **SC-004**: The existing 290-test suite (post-feature-015) continues to pass at 290 passed, with new ESPHome-transport tests (≥ 10) added on top. Measured by `pytest tests/ -q` exit code zero across 3 consecutive full runs.
- **SC-005**: `grep -rE 'transports/esphome' src/aivg_core/platforms/` returns zero matches — the new transport code lives entirely OUTSIDE the platform plugins. Measured by a new grep-gate regression test (`tests/unit/test_no_transport_imports_in_platforms.py`).
- **SC-006**: 4 concurrent ESPHome devices each completes a voice turn within 1.5 × the single-device latency budget — proving the transport is non-blocking. Measured by a new concurrency integration test (mirror of feature-015's `test_sc005_ten_plus_concurrent_sessions`).
- **SC-007**: An ESPHome device that disconnects mid-turn does NOT leak resources — the gateway's open-socket / open-task count returns to baseline within 5 seconds. Measured by an integration test that opens 100 sessions, drops each one mid-turn, and asserts task-count stability.
- **SC-008**: The new transport adds ≤ 1000 lines of net production source to `aivg_core/` — excluding any code in the `aioesphomeapi` PyPI dependency, which is consumed as-is, not vendored. Measured by `git diff --stat`.

<!-- Open Questions section removed: Q1-Q3 resolved in /speckit-clarify, see ## Clarifications above. -->

