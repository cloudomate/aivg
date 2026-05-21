# Feature Specification: `@aivg/sat-sdk` (TypeScript)

**Feature Branch**: `014-aivg-sat-sdk-ts`
**Created**: 2026-05-20
**Status**: Draft
**Input**: User description: "ship `@aivg/sat-sdk` (TypeScript) — a portable npm package extracted from clients/electron-test that consumes the AIVG satellite contract end-to-end: control-plane WS (register/heartbeat/config/commands/logs), WebRTC voice-plane (offer/answer + Opus), state machine (idle/listening/speaking/error), adoption flow (PENDING → ADOPTED), config push/pull, OTA hooks, and skill/agent intent helpers (tool-call progress + skill events surfaced to consumers). Browser + Electron + Node targets, no native deps, TypeScript types first-class. Lives at sdks/typescript/ in the monorepo. Refactor clients/electron-test to consume the new package as the first integration test. Out of scope for v1: browser wake-word, C++ SDK (separate feature), ESP32 firmware (separate feature)."

## Background & Motivation

The Electron test client (`clients/electron-test/`) is the only validated consumer of the AIVG satellite contract today. Its WebRTC + control-plane wiring works end-to-end (proven live during feature 013 testing), but it lives inside a one-off test harness — no other application (PWA, third-party Electron app, headless Node fleet operator, browser-based dashboard) can reuse it without copy-pasting.

A device builder who wants to ship a software-based AIVG satellite (desktop assistant, kiosk PWA, headless smoke-tester) today must reverse-engineer the protocol from the test client + the management-plane source + the WebRTC offerer flow described in [docs/generic-voice-satellite-design.md](docs/generic-voice-satellite-design.md). That is both an adoption obstacle and a maintenance hazard — the next protocol revision can silently break out-of-tree consumers.

Releasing the SDK as an installable npm package turns an internal implementation detail into a stable, documented integration surface. It also lays the contract foundation for the planned C++ SDK (feature 015): same protocol, same state machine, same JSON shapes — only the transport bindings differ.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Device builder ships a working voice satellite in their own app (Priority: P1) 🎯 MVP

A developer building a voice-enabled application (Electron desktop app, browser PWA, Node-based smoke-tester) installs the package, writes a few dozen lines of code, and ends up with a satellite that can register against an AIVG gateway, make a voice call, stream audio in both directions, and tear down cleanly. They never have to read the underlying WebRTC offer/answer protocol or the JSON wire format.

**Why this priority**: this is the table-stakes "the package is useful at all" path. Every subsequent story depends on it.

**Independent Test**: a fresh demo app (under `sdks/typescript/examples/`) that imports the published-locally package, connects to a running AIVG gateway, plays a recorded synthetic audio prompt into the SDK, and demonstrates the round-trip transcript-and-reply within a single voice turn. No fleet/skill features required for this story.

**Acceptance Scenarios**:

1. **Given** a running AIVG gateway and a fresh project with the SDK installed, **When** the developer constructs a `Satellite` with the gateway URL and calls connect/beginSession/endSession in the documented sequence, **Then** the gateway logs show one full voice turn (register → WebRTC offer/answer → STT → agent loop → TTS → audio out) and the SDK's state machine reports `idle → listening → speaking → idle`.
2. **Given** the SDK is consumed from an Electron renderer process, **When** the application requests microphone permission and starts a session, **Then** captured microphone audio reaches the gateway and synthesised audio is played back through the host audio output without the developer wiring any WebRTC primitives directly.
3. **Given** the SDK is consumed from a Node.js test runner with a developer-provided WebRTC implementation injected, **When** the test loads a pre-recorded PCM file as the input source, **Then** the test can assert on the resulting transcript event without needing a real microphone or speaker.

---

### User Story 2 — Fleet operator manages SDK-based satellites via the existing AIVG CLI (Priority: P2)

An operator who has SDK-based satellites running (PWAs, Electron desktop apps) wants to see them in `aivg list`, push config changes (wake word, routing mode, log level), receive status heartbeats, observe live logs, and command them (reboot / refresh) — exactly as they can today with the Electron test client. This means the SDK has to be a complete management-plane citizen, not just a voice transport.

**Why this priority**: without fleet management parity, SDK-based satellites are second-class — the operator has to maintain two mental models. This is what unlocks productionising browser/Electron satellites.

**Independent Test**: a demo app started with the SDK shows up in `aivg list` as `online / adopted`, accepts a `aivg device config set` change and applies it (verified by the SDK's event surface), and replays its logs into `aivg logs <device>` while a voice session is in progress.

**Acceptance Scenarios**:

1. **Given** an SDK-based satellite is running with `pending` adoption state, **When** an operator runs `aivg device adopt <id>`, **Then** the satellite transitions to `adopted` and the SDK emits an adoption-state event the consumer can observe.
2. **Given** an `adopted` satellite is running with default config, **When** the operator pushes a new config via the management CLI, **Then** the SDK delivers a config-changed event with the new values and the operator can verify the change took effect by reading `aivg device config get`.
3. **Given** the satellite is running, **When** any log event is produced by the gateway for that device, **Then** `aivg logs <device>` streams it via the existing log endpoint and the SDK does not block the operator from reading them.
4. **Given** the satellite is running, **When** an operator issues a `reboot` command via the CLI, **Then** the SDK surfaces the command to the consumer application via an event with the verb and arguments, and the consumer can implement the response semantics appropriate to its host environment.

---

### User Story 3 — Agent UI surfaces what the agent is doing during a turn (Priority: P3)

A developer building a chat-style or visual UI on top of the SDK wants to show the user what the agent is doing in real time: which tools it called, which skill it loaded, the partial assistant text as it streams. Without this, the UI is a voice-only black box — the user just hears speech and has no visual feedback for tool-using turns (e.g., "looking up the weather …").

**Why this priority**: this elevates the SDK from a voice transport to a full agent client. It also distinguishes a browser-based AIVG client from a generic WebRTC mic — there is no other way to surface this telemetry to a UI.

**Independent Test**: a demo voice turn whose response involves a tool call (e.g., the agent uses a web-search tool) produces a sequence of tool-call-started, tool-call-completed, and partial-transcript events at the SDK's event surface; the demo UI renders them in order.

**Acceptance Scenarios**:

1. **Given** an in-flight voice turn whose agent loop invokes one or more tools, **When** the tool events are emitted by the gateway, **Then** the SDK forwards each tool's start / complete event to the consumer with the tool name and (where available) a brief result summary.
2. **Given** an in-flight voice turn whose agent loads a skill mid-turn, **When** the skill-loaded event reaches the SDK, **Then** the consumer receives a skill-loaded event with the skill name and source (built-in / plugin / tap).
3. **Given** an in-flight voice turn that produces a streamed text reply, **When** text deltas arrive from the gateway, **Then** the SDK surfaces partial-transcript events that a UI can append to a chat bubble while the audio is still synthesising.

---

### User Story 4 — The Electron test client is refactored to consume the new package as the first real integration test (Priority: P2)

The Electron test client (`clients/electron-test/`) is rewritten to consume `@aivg/sat-sdk` instead of inlining its own WebRTC / WebSocket code. This proves the package's API covers everything the test client needs and provides a continuously-runnable integration sanity check.

**Why this priority**: dog-fooding catches API gaps that "blank-page" examples would miss. It also removes a forked code path the next protocol revision would have to keep in sync.

**Independent Test**: the refactored Electron test client achieves byte-equivalent end-to-end behaviour (registers, makes a voice call, displays transcript, replays logs) against the same gateway as the current pre-refactor version.

**Acceptance Scenarios**:

1. **Given** the Electron test client refactored onto the SDK, **When** it is launched against a running AIVG gateway, **Then** it shows up in `aivg list` as `online / adopted` and successfully completes a voice turn (matching the current client's behaviour verified earlier in feature 013 live testing).
2. **Given** the refactor is complete, **When** a developer reads `clients/electron-test/renderer.js`, **Then** every WebRTC / WebSocket primitive call has been replaced by a method call on the SDK, and the test client contains no protocol-level logic of its own.

---

### Edge Cases

- **Network drop during an active voice turn**: the SDK MUST end the in-flight session cleanly (no orphan WebRTC peer connection, no orphan WS reconnect spamming) and surface a transient-error event the consumer can render. Reconnect of the control plane resumes once the network is back.
- **Browser microphone permission denied**: `beginSession()` MUST surface a permission-denied error without leaving the SDK in `listening` state.
- **Multiple consumer calls to `beginSession()` with one in flight**: the second call MUST resolve to the existing session rather than starting a second WebRTC peer connection (idempotent).
- **Adoption state of `pending` when consumer tries `beginSession()`**: the SDK MUST surface a `not_adopted` error; voice cannot start until the operator approves the device.
- **Gateway URL is `http://` and the consumer page is `https://`**: the SDK MUST surface a mixed-content error with a clear remediation hint (use HTTPS gateway, or develop on `localhost`).
- **WebRTC ICE fails (no candidate pair)**: the SDK MUST surface an ICE-failed error, tear down the peer connection, return to `idle`, and NOT auto-retry. The consumer decides whether to retry.
- **Page reload during a session**: the previous WebRTC peer connection is closed by the browser; the SDK's next instance MUST detect the prior session at the gateway and recover or cleanly re-adopt without leaving a ghost in `aivg list`.
- **OTA notification arrives during a voice session**: the SDK MUST forward the OTA event to the consumer but MUST NOT auto-disconnect the voice session (the consumer decides; browser / Electron OTA is application-side, not flash-side).
- **Same `deviceId` connecting from two tabs simultaneously**: the SDK MUST forward whatever the gateway decides (last-write-wins or duplicate-device error) and MUST NOT silently re-key the connection.
- **Gateway protocol version mismatch**: the SDK MUST include its own contract version in the registration handshake and surface a protocol-mismatch error if the gateway reports an incompatible contract version.

## Requirements *(mandatory)*

### Functional Requirements

#### Adoption & discovery

- **FR-001**: The package MUST allow a consumer application to register a satellite with the AIVG gateway, automatically navigating the `pending → adopted` flow when the operator approves the device.
- **FR-002**: The package MUST surface the current adoption state to the consumer at all times and emit a state-change event whenever it transitions.
- **FR-003**: The package MUST allow the consumer to provide a stable `deviceId` and `deviceType` that appear in `aivg list` consistently with the existing Electron test client today.

#### Control plane

- **FR-004**: The package MUST maintain a long-lived control connection to the gateway with automatic reconnect using exponential back-off and a maximum back-off ceiling.
- **FR-005**: The package MUST send periodic heartbeats containing the current device state at the cadence the gateway expects (per the management contract).
- **FR-006**: The package MUST deliver `config_changed`, `command`, and `log_entry` messages to consumer-supplied event handlers without requiring polling.
- **FR-007**: The package MUST allow the consumer to read and update the satellite's configuration (wake word, routing mode, log level) via a typed configuration API.

#### Voice plane

- **FR-008**: The package MUST establish a WebRTC session against the gateway when the consumer calls a documented "begin session" entry point, completing offer/answer + ICE without exposing those primitives to the consumer.
- **FR-009**: The package MUST stream microphone audio up to the gateway and play received audio down (in browser/Electron targets) without the consumer wiring `RTCPeerConnection` directly.
- **FR-010**: The package MUST allow the consumer to inject an alternative WebRTC implementation (for Node.js / test environments) at construction time, so headless tests do not require a real microphone.
- **FR-011**: The package MUST support push-to-talk timing (consumer-controlled start/end) as the v1 ingress.
- **FR-012**: The package MUST end the session cleanly on consumer request, releasing all WebRTC and audio resources.

#### State machine

- **FR-013**: The package MUST expose a state machine with at least the following observable states: `idle`, `listening`, `speaking`, `error`; and emit a state-change event for every transition.
- **FR-014**: The package MUST treat its state machine as the single source of truth (consumers MUST NOT need to derive state from independent event streams).

#### Skill / agent intents

- **FR-015**: The package MUST forward tool-call started, tool-call completed (with result summary where available), and tool-call failed events from the gateway to consumer event handlers.
- **FR-016**: The package MUST forward skill-loaded events from the gateway with the skill name and source.
- **FR-017**: The package MUST forward partial-transcript text deltas to consumer event handlers as the agent streams its reply.

#### OTA hooks

- **FR-018**: The package MUST forward OTA manifests arriving on the control plane to a consumer event handler without auto-applying them; the consumer (browser/Electron app) decides what "apply OTA" means for its host environment.

#### Reliability & error surface

- **FR-019**: The package MUST surface fatal errors (control plane permanently dropped, WebRTC failed, protocol mismatch, permission denied) via a single typed error event that includes a machine-readable code + a human-readable message.
- **FR-020**: The package MUST reconnect the control plane automatically on transient network drops without losing the consumer's registered event handlers.

#### Logs

- **FR-021**: The package MUST forward gateway-pushed `log_entry` messages for the consumer's own device to a consumer event handler, so consumer apps can display agent-side activity in their own UI.

#### Packaging & target environments

- **FR-022**: The package MUST publish under a discoverable scope name and include TypeScript type declarations as first-class artefacts (not added separately or in a sibling `@types/` package).
- **FR-023**: The package MUST work in modern browsers (those supporting `RTCPeerConnection` + `WebSocket` + `MediaDevices.getUserMedia`), in Electron renderer and main processes, and in Node.js 20+ when a WebRTC implementation is injected.
- **FR-024**: The package MUST NOT require native compiled dependencies (no `node-gyp`, no platform-specific binaries) so installation is identical on macOS, Linux, and Windows.
- **FR-025**: The package MUST ship under a `sdks/typescript/` directory within the existing AIVG monorepo so protocol changes can be co-changed with gateway changes in a single PR.

#### Integration test surface

- **FR-026**: The existing `clients/electron-test/` application MUST be refactored to consume the new package as its only protocol implementation; it MUST NOT contain any direct WebRTC / WebSocket protocol code after the refactor.
- **FR-027**: The refactored Electron test client MUST achieve functional parity with its current behaviour (registers, makes a voice call, displays transcript, surfaces logs) when run against the same gateway.

#### Out of scope (v1)

- **OOS-001**: Browser-side wake word (e.g., openWakeWord-WASM, Porcupine-Web). PTT only in v1; the wake-word adapter contract is a future additive surface.
- **OOS-002**: C++ SDK (`libaivg-sat`) — separate feature (planned 015).
- **OOS-003**: ESP32 firmware ports (XIAO + ATOM Echo) — separate feature (planned 016).
- **OOS-004**: RPi reference port — separate feature (later).
- **OOS-005**: Multi-tenant authentication / API keys / token-based device registration. v1 inherits the same auth model the existing Electron test client uses today.

### Key Entities

- **Satellite**: the top-level handle a consumer application instantiates. Owns the device identity, the control-plane connection, the voice-session lifecycle, and the event surface.
- **SatelliteState**: the observable lifecycle state (`idle | listening | speaking | error`). One value at a time; transitions emit events.
- **AdoptionState**: the device's adoption status with the gateway (`pending | adopted`). Mirrors feature 011's existing concept and persists across SDK sessions.
- **SatelliteConfig**: the configuration values pushed/pulled via the management plane (wake word, routing mode, log level, heartbeat interval — same shape as the existing `aivg device config` payload).
- **VoiceSession**: a single voice-call lifecycle from `beginSession()` to `endSession()`. Has a session id, optional turn metadata, and feeds the state machine.
- **CommandEvent**: an operator-issued command arriving over the control plane (`reboot`, `restart`, etc.) — the consumer decides how to respond in its host environment.
- **ToolCallEvent**: telemetry forwarded from the agent layer about tools the agent invoked during a turn.
- **SkillEvent**: telemetry forwarded about skills the agent loaded mid-turn.
- **TranscriptDelta**: a partial text update from the streaming agent reply, intended for chat-style UI updates.
- **LogEntry**: a gateway-pushed log line scoped to this device, with level + source + message + timestamp.
- **OtaManifest**: metadata describing an available OTA bundle. The SDK forwards it; the consumer decides on the host-environment-appropriate action.
- **SdkError**: typed error with a machine-readable code (`permission_denied | ice_failed | ws_disconnected | mixed_content | not_adopted | protocol_mismatch | …`) and a human-readable message.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer new to AIVG can write a working satellite in under 50 lines of application code (excluding UI markup), from "fresh install" to "successful voice turn against a running gateway".
- **SC-002**: The refactored `clients/electron-test/` is functionally indistinguishable from its current pre-refactor behaviour when run against the same gateway, and contains no direct WebRTC or WebSocket protocol code in application files.
- **SC-003**: After a transient network drop of up to 30 seconds, the SDK's control plane reconnects and registered event handlers continue receiving events without the consumer re-subscribing.
- **SC-004**: All public surface of the package is described by TypeScript type declarations; no `any` appears in any exported type signature.
- **SC-005**: The package installs successfully on macOS, Linux, and Windows with one install command and requires no compile step or platform-specific binaries.
- **SC-006**: Loading the package in a browser, Electron renderer, Electron main, and Node.js 20+ produces zero runtime errors at import time across all four targets.
- **SC-007**: The published contract surface (event names, state machine state names, error codes, configuration field names) matches the existing `aivg --contract-version 1.0.0` shape; the SDK release does NOT require a contract bump.
- **SC-008**: A demo voice turn whose agent invokes at least one tool surfaces all expected events (tool-call-started, tool-call-completed, partial-transcript deltas, state transitions) at the SDK event surface within 200 ms of when the gateway emits them.
- **SC-009**: The Electron test client refactor reduces its application-code line count by at least 30% (since protocol logic moves into the SDK).
- **SC-010**: Operators using `aivg list`, `aivg device config set/get`, `aivg logs`, and `aivg device command` against an SDK-consumer satellite get the same results they would against the pre-SDK Electron test client (full management-plane parity).

## Assumptions

- The AIVG gateway is feature 013-installed and feature 011-management-plane-current (contract version `1.0.0`); the SDK targets that contract surface unchanged.
- Consumers are responsible for their own UI; the SDK is headless and event-driven.
- Consumers handle wake-word / mic activation in their host environment. The v1 ingress is push-to-talk; openWakeWord-WASM (or any other browser wake-word) is a future additive surface.
- The Electron test client's current behaviour (validated live in feature 013 — voice turns complete end-to-end against a running gateway) is the reference behaviour the refactored client must match.
- WebRTC is available natively in browsers / Electron; for Node.js targets, the consumer provides a WebRTC implementation at construction time (the SDK does not bundle one).
- Browser-side echo cancellation, noise suppression, and AGC are handled by the user agent (via `getUserMedia` constraints) — the SDK enables these constraints by default but does not implement DSP itself.
- Adoption auth in v1 follows the existing Electron test client model: any device registering with the gateway gets the `pending` state and requires an operator to adopt via `aivg device adopt`. No API keys or tokens.
- TLS / production deploy concerns (HTTPS gateway, WSS) are gateway-side; the SDK transparently uses whichever scheme the gateway URL specifies.
- Browser microphone permission UX is consumer-handled; the SDK surfaces a clear error code when permission is denied but does not implement permission-request UI.
- Same-device duplicate registration (two tabs of the same `deviceId`) is gateway-arbitrated; the SDK does not implement client-side deduplication.

## Dependencies

- AIVG gateway (`aivg setup`-installed Hermes plugin, feature 013) running and reachable from the consumer host.
- Management plane contract (feature 011) at version `1.0.0`.
- Existing Electron test client (`clients/electron-test/`) is the live reference implementation whose behaviour the refactored consumer must preserve.
