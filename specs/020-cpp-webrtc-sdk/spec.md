# Feature Specification: libaivg-sat-embedded (C++ WebRTC Satellite SDK for PSRAM-class devices)

**Feature Branch**: `020-cpp-webrtc-sdk`
**Created**: 2026-05-22
**Status**: Draft
**Input**: User description: "c++ sdk for esp32/rpi2w kind of devices with psram 4mb and above , webrtc as transport"

## Context & relationship to prior work

This feature supersedes the `016-cpp-sdk` draft (never merged) by making
two decisions that `016` deferred to clarification:

1. **Transport is committed to WebRTC.** `016`'s Q4 (full WebRTC vs a
   WebSocket-tunneled Opus variant vs deferring the MCU tier) is resolved:
   every supported device speaks the gateway's existing WebRTC voice plane.
   No new wire-protocol variant is introduced, so the frozen wire contract
   is not bumped by this feature.
2. **The target floor is small, PSRAM-equipped devices.** The primary
   audience is no longer "Raspberry Pi 4/5 desktop class" but the cheaper,
   more constrained tier: ESP32-S3-class microcontrollers with PSRAM
   (≥ 4 MB) and Linux single-board computers of the Raspberry Pi Zero 2 W
   class. The SDK must fit and perform on these constrained targets, not
   just on a developer laptop.

The public C++ API surface remains the byte-shape sibling of the
TypeScript SDK (`@aivg/sat-sdk`, feature 014) — the same satellite-side
contract, expressed in C++ for native-binary and firmware targets.

## Clarifications

### Session 2026-05-22

- Q: Is the ESP32-S3 (MCU) tier in-scope for v0.1, or sequenced after the Linux tier? → A: MCU first — the ESP32-S3 tier is the lead MVP (US2); the RPi Zero 2 W Linux tier (US1) becomes the supporting/lower-risk validation tier. Both ship in v0.1.
- Q: Which embedded WebRTC stack underpins the ESP32-S3 tier? → A: A third-party ESP32 WebRTC project under a permissive OSI license (MIT/Apache) — selected because Espressif's own WebRTC solution depends on `esp-adf-libs` components under the product-locked "Espressif Modified MIT" license (`LicenseRef-Espressif-Modified-MIT`), which forbids redistribution for non-Espressif products and is therefore not usable. The reference candidate is `libpeer` (MIT), which also supports the Linux/RPi tier — enabling one transport library across both tiers.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A maker builds a satellite on a Linux small-board (Raspberry Pi Zero 2 W class) (Priority: P1)

A hobbyist or hardware vendor wants a pocket-sized voice satellite built
on a Linux single-board computer of the Raspberry Pi Zero 2 W class
(quad-core ARM, ~512 MB RAM, Wi-Fi). They link libaivg-sat into a small
C++ program they write themselves, feed it microphone PCM from their own
audio driver, receive reply PCM back, and play it through their own
speaker driver. One full push-to-talk voice turn completes against a
running AIVG gateway over WebRTC — with no Python, Node, or Electron on
the device.

**Why this priority**: this tier runs a full POSIX userland on the same
third-party WebRTC library chosen for the MCU tier (`libpeer`, which
supports Linux/RPi as well), so it carries the least transport risk and
serves as the lower-risk validation path that de-risks the MCU lead
(US2). Both tiers ship in v0.1; per the 2026-05-22 clarification the MCU
tier is the MVP lead and this Linux tier is its supporting validation
target.

**Independent Test**: a reference sample in `sdks/cpp/examples/` reads
WAV bytes as a stand-in for live mic audio, drives one PTT voice turn
against a running AIVG gateway, and writes the reply audio to a WAV
file. The transcript and reply-audio events fire exactly as observed
from the same gateway the electron-test consumes.

**Acceptance Scenarios**:

1. **Given** `sdks/cpp/` checked out on a Raspberry Pi Zero 2 W class board, **When** the developer runs the documented build, **Then** the build produces the satellite library plus a smoke-test sample binary using only a C++ toolchain and the project's own dependency fetch (no system package manager beyond what the build tool fetches).
2. **Given** the built smoke binary pointed at a running gateway, **When** the developer signals "PTT pressed" then "PTT released" around a spoken phrase, **Then** the gateway completes one voice turn and the sample reports the transcript and writes non-empty reply audio.
3. **Given** a long-lived voice session, **When** the gateway emits a state change (e.g., `adopted → idle`), **Then** the consumer receives an event whose payload mirrors the TypeScript SDK's shape (`previous → current`).

---

### User Story 2 — An embedded developer builds a satellite on an ESP32-S3-class MCU with PSRAM (Priority: P1) 🎯 MVP

An embedded developer builds a voice satellite on an ESP32-S3-class
microcontroller (Xtensa, RTOS, no operating system, PSRAM ≥ 4 MB,
Wi-Fi). They consume the **same public C++ API** as the Linux small-board
tier — same class, same methods, same events — and complete one PTT
voice turn over WebRTC against the same gateway. Differences from the
Linux tier are confined to build-time configuration (transport profile,
threading, memory ceilings), never the API.

**Why this priority**: this is the MVP lead (per the 2026-05-22
clarification, "MCU first"). The sub-$10 MCU story is the entire reason
to target "PSRAM-class devices"; a C++ SDK that only ran on Linux boards
would be redundant with the existing TypeScript path on bigger hardware.
The PSRAM requirement is precisely the floor that makes a WebRTC stack
(ICE + DTLS-SRTP + Opus) plausible on an MCU. It carries materially more
transport and build risk than US1, which is why the lower-risk Linux
tier ships alongside it as the validation path — but the MCU tier is the
binding success gate for v0.1.

**Independent Test**: a reference firmware project in
`sdks/cpp/examples/esp32s3_smoke/` builds under the chosen embedded
toolchain and, flashed to an ESP32-S3 board with PSRAM and Wi-Fi,
registers with the gateway, adopts, and completes one PTT voice turn
end-to-end (mic → STT → agent → TTS → speaker). The public API calls in
the firmware are identical to those in the US1 sample.

**Acceptance Scenarios**:

1. **Given** an ESP32-S3 board with ≥ 4 MB PSRAM and Wi-Fi, **When** the developer builds and flashes the embedded smoke firmware, **Then** the device registers, adopts, and completes one PTT voice turn over WebRTC against the same gateway US1 hits.
2. **Given** the embedded smoke firmware, **When** the developer calls the SDK's session and PTT methods, **Then** the API surface (class name, method signatures, event payloads) is identical to the US1 tier; only documented build-time flags differ.
3. **Given** a board that is below the PSRAM floor (no PSRAM, or < 4 MB), **When** the developer consults the supported-hardware matrix, **Then** the board is clearly listed as unsupported with the reason (insufficient memory for the WebRTC media stack).

---

### User Story 3 — Wire-protocol parity with `@aivg/sat-sdk` (Priority: P1)

The C++ SDK presents the same wire surface to the gateway as the
TypeScript SDK: same management-plane WebSocket frames, same REST
endpoints, same WebRTC offer/answer handshake. A device running
libaivg-sat and a browser running `@aivg/sat-sdk` are indistinguishable
to the gateway at the message-shape level.

**Why this priority**: the satellite-side wire surface is a frozen
contract. Diverging here would force a contract-version bump and risk
breaking the existing TypeScript/Electron clients. Parity is what lets
this SDK reuse the entire gateway unchanged.

**Independent Test**: gateway logs from a libaivg-sat turn and an
`@aivg/sat-sdk` turn against the same gateway are equivalent in message
type, field names, and ordering (only payload values such as timestamps
and session IDs differ). The gateway's advertised contract version is
unchanged by this feature.

**Acceptance Scenarios**:

1. **Given** an SDK consumer that registers, opens a session, and toggles mute/unmute, **When** the gateway receives the traffic, **Then** the inbound message shapes match those produced by the current `@aivg/sat-sdk` against the same gateway.
2. **Given** the gateway's advertised contract version, **When** the libaivg-sat consumer reads the version envelope on connect, **Then** the SDK accepts it as compatible when the major version matches and warns (without crashing) on a mismatch.

---

### User Story 4 — A new contributor builds and runs the reference sample on a developer machine in minutes (Priority: P2)

A contributor with no embedded hardware on hand clones the repo, builds
the Linux/macOS reference sample, and runs one voice turn against a
local gateway quickly — proving the SDK is consumable by anyone with a
standard C++ toolchain, and giving the project a living integration test
(the role `clients/electron-test/` plays for feature 014).

**Why this priority**: a library nobody can build is a library nobody
can verify. The desktop reference sample is the everyday regression
gate; the on-hardware smokes (US1/US2) run less often.

**Independent Test**: on a stock Linux or macOS developer machine with
only a C++ toolchain and the build tool installed, the documented build
succeeds and the sample completes one turn against a local gateway.

**Acceptance Scenarios**:

1. **Given** a fresh checkout on a stock Linux or macOS machine, **When** the contributor follows the README build steps, **Then** the sample binary builds without manual dependency resolution beyond what the build tool fetches.
2. **Given** the built sample and a local gateway, **When** the contributor runs one turn, **Then** the transcript prints and reply audio is written, matching US1's behavior.

---

### Edge Cases

- **Gateway unreachable / refused at connect** — surfaced as a typed error event with a stable code, then automatic management-plane reconnect with backoff; never a crash.
- **Reply media never arrives within the timeout** — surfaced as a typed media-timeout event; the session can be retried without restarting the device.
- **PTT pressed before the session is ready, or unmute/mute called out of order** — handled as a no-op or typed transient error, not a crash.
- **Double connect / double session** — the second call is rejected or coalesced deterministically, with a documented outcome.
- **PSRAM exhaustion on the MCU during a turn** — surfaced as a typed error and a clean session teardown rather than a watchdog reset, where the platform allows.
- **Wi-Fi drop mid-turn on a constrained device** — the in-flight turn ends with a typed error; the SDK returns to a state from which a new turn can begin once connectivity returns.
- **Barge-in (device speaks while reply audio is playing)** — the in-progress playback is stopped and a barge-in event is delivered, matching the TypeScript SDK's behavior.

## Requirements *(mandatory)*

### Functional Requirements

#### Public API surface

- **FR-001**: The SDK MUST expose a single primary satellite object constructed from a configuration struct (gateway URL, optional separate signaling URL, device ID, device name, device type, firmware version) and a set of caller-supplied callbacks/handlers.
- **FR-002**: The SDK MUST expose lifecycle operations mirroring the TypeScript SDK: connect, disconnect, begin session, end session, mute, unmute, plus inspectors for current state, adoption status, and microphone-live status.
- **FR-003**: The SDK MUST emit typed events mirroring the TypeScript SDK (adoption, state, gateway state, transcript, log, error, transient error, session ended, barge-in). Each payload MUST match the TypeScript SDK at the field-name and type level.
- **FR-004**: The SDK MUST report errors as a typed set with stable string codes matching the TypeScript SDK (e.g., connection refused, signaling failed, ICE gathering timeout, media track timeout, missing audio-input callback, internal WebRTC error). Code strings are part of the contract.
- **FR-004a**: The SDK MUST expose the **same public API across both device tiers** (Linux small-board and ESP32-S3-class MCU). Tier-specific behavior (transport profile, threading model, memory ceilings) MUST be selected at build time via documented configuration flags — never at run time, never as a divergent API.

#### Audio I/O boundary

- **FR-005**: The SDK MUST accept caller-provided microphone audio through a documented callback (PCM16 mono; sample rate negotiated at session start). The SDK MUST NOT bundle or link a system audio backend.
- **FR-006**: The SDK MUST deliver reply audio to a caller-provided output callback (PCM16 mono). The consumer owns the speaker driver.
- **FR-007**: A reference sample MAY bundle a single-file/header-only audio backend for demonstration, but that bundling MUST stay within `examples/`, not the SDK proper.

#### Transport (WebRTC, committed)

- **FR-008**: Voice media MUST flow over the gateway's existing WebRTC voice plane on every supported device. No alternative transport (e.g., WebSocket-tunneled audio) is introduced by this feature.
- **FR-009**: The SDK MUST follow the gateway's established WebRTC offer/answer pattern: the client offers with ICE gathering complete, posts the SDP to the voice-plane signaling endpoint, and applies the gateway's answer. The signaling URL MUST be configurable separately from the management URL.
- **FR-010**: The SDK MUST use the long-lived voice session with mute/unmute PTT model (the peer connection is NOT torn down per PTT cycle, to avoid racing the gateway's silence detector).
- **FR-011**: The SDK MUST tolerate the documented gateway response-shape variants (e.g., fabricating a local session identifier when the gateway returns only an answer SDP).
- **FR-012**: WebRTC media MUST be encrypted per the standard handshake (DTLS-SRTP); the SDK MUST NOT require the gateway to accept unencrypted media. On the MCU tier this implies the device performs the DTLS handshake and SRTP within its memory budget.

#### Wire-protocol parity & versioning

- **FR-013**: The SDK MUST consume the gateway's current frozen wire contract verbatim — no new HTTP endpoint, no new WS message type, no new SDP munging. This feature MUST NOT cause a contract-version bump.
- **FR-014**: On connect, the SDK MUST read the gateway's advertised contract-version envelope, accept it when the major version matches, and emit a clear warning (without aborting) on a mismatch.

#### Lifecycle, reconnect, errors

- **FR-015**: The SDK MUST implement management-plane reconnect with exponential backoff plus jitter, capped at a documented ceiling. A dropped management connection MUST be retried automatically; the consumer observes only gateway-state transitions, not raw network errors.
- **FR-016**: The SDK MUST surface all enumerated edge cases as typed events rather than crashes or undefined behavior.

#### Packaging, build & supported hardware

- **FR-017**: The Linux/macOS/RPi-Zero-2-W tier MUST be buildable with a mainstream C++ build configuration (CMake 3.20+ class), consumable by downstream projects via source inclusion and dependency-fetch without a mandatory system-wide install step.
- **FR-018**: The ESP32-S3-class tier MUST be buildable into a flashable firmware image via its standard embedded toolchain (ESP-IDF v5.x class), reusing the same SDK sources and public headers as the Linux tier. The WebRTC transport MUST be provided by a third-party embedded WebRTC implementation under a permissive OSI license (MIT or Apache-2.0) — reference candidate `libpeer` (MIT), which targets ESP32 and Linux/RPi alike. The SDK MUST NOT depend on Espressif's `esp-adf-libs`-based WebRTC solution, whose components are under the product-locked "Espressif Modified MIT" license that prohibits redistribution for use with non-Espressif products.
- **FR-019**: The SDK MUST ship a `README.md` documenting (a) the public API, (b) build steps per tier, (c) at least one runnable smoke recipe per tier, and (d) a supported-hardware matrix that names the PSRAM floor (≥ 4 MB) and explicitly lists excluded boards.
- **FR-020**: Every public symbol MUST carry a documentation comment block; generated API docs are optional but the source comments are required.

#### Quality gates

- **FR-021**: A desktop/Linux smoke sample MUST drive one voice turn against a running gateway end-to-end; its result is the binding pass/fail for the wire-parity gate (US3) and the everyday regression gate (US4).
- **FR-022**: The typed-error paths (at least connection refused, signaling failed, ICE gathering timeout) MUST be regressable deterministically — via a test directory or the smoke binary against a recorded/mock gateway — without requiring live hardware.
- **FR-023**: At least one on-hardware smoke MUST exist per device tier (one Linux small-board, one ESP32-S3-class) and complete one voice turn, demonstrating the same mic → STT → agent → TTS → speaker cycle.

#### Scope boundaries

- **OOS-001**: Microcontrollers without PSRAM, or with < 4 MB PSRAM, and any board lacking Wi-Fi/TLS-capable resources (e.g., classic ESP32 without PSRAM, 8-bit AVR/Arduino UNO/Mega/Nano). Permanently out of scope — insufficient memory for the WebRTC media stack.
- **OOS-002**: Any change to the gateway, the management-plane REST surface, the WebRTC handshake shape, the satellite-side wire protocol, or the TypeScript SDK. This feature is satellite-client-side only.
- **OOS-003**: A bundled audio backend in the SDK proper; the SDK is a thin protocol layer. The reference sample's audio backend lives in `examples/`.
- **OOS-004**: A C ABI / FFI shim (for Rust, Go, Swift consumers). C++ only for this version; a C shim is a possible follow-up.
- **OOS-005**: An OTA-update implementation. The SDK MUST forward OTA-related events to the consumer, but the consumer owns the update flow.
- **OOS-006**: Package-manager ports (vcpkg / Conan) and Windows support. Possible follow-ups; not required here.

### Key Entities

- **Satellite** — the SDK's primary object. Owns one management-plane connection and at most one active WebRTC voice session. Holds current state, adoption status, and mic-live status.
- **SatelliteOptions** — configuration struct (gateway URL, optional signaling URL, device identity, callbacks, timeouts).
- **AudioInputCallback** — caller-provided source yielding the next PCM16 mono microphone frame (or end-of-stream).
- **AudioOutputCallback** — caller-provided sink consuming one PCM16 mono frame for playback.
- **SatEvent** — the discriminated event delivered to the consumer (adoption, state, gateway state, transcript, log, error, transient error, session ended, barge-in).
- **SatError** — a typed error carrying a stable code string, a human-readable message, and optional context.
- **Device tier (build-time profile)** — the selected target class (Linux small-board vs ESP32-S3-class MCU) that picks transport/threading/memory settings without changing the public API.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: One voice turn (PTT press → speak → release → reply audio) completes end-to-end against the same running gateway the electron-test consumes, verified by the desktop smoke producing non-empty reply audio within 15 seconds of release.
- **SC-002**: One voice turn completes on at least one Raspberry Pi Zero 2 W class board (US1) within 20 seconds of the first PTT press.
- **SC-003**: One voice turn completes on at least one ESP32-S3 board with ≥ 4 MB PSRAM (US2) within 30 seconds of the first PTT press, demonstrating the same mic → STT → agent → TTS → speaker cycle. (The MCU latency budget is intentionally looser than the Linux tiers.)
- **SC-004**: The SDK's public API surface (the six lifecycle operations plus the full TypeScript event set — currently 17 events) matches the TypeScript SDK 1:1 by name, argument count, and event-payload field set, documented in a side-by-side README table.
- **SC-005**: The wire-shape difference between a libaivg-sat turn and a `@aivg/sat-sdk` turn against the same gateway is zero at the message-type and field-name level (only payload values such as timestamps and session IDs differ).
- **SC-006**: The gateway's advertised contract version is unchanged after this feature lands; the gateway's REST and WS handlers are not modified.
- **SC-007**: A contributor with no embedded hardware can clone the repo, follow the README, build the desktop sample, and run one turn against a local gateway in ≤ 30 minutes of total wall-clock time including reading the doc.
- **SC-008**: The supported-hardware matrix in the README correctly classifies a tested in-floor board (ESP32-S3 + ≥ 4 MB PSRAM) as supported and a tested below-floor board (no/insufficient PSRAM) as unsupported.
- **SC-009**: Net committed repository growth from this feature (SDK source + samples + docs, excluding fetched dependencies) is small enough to review in one sitting (target ≤ 1 MB).

## Assumptions

- **Two device tiers, one public API, one transport library.** The Raspberry Pi Zero 2 W class runs a full POSIX userland; the ESP32-S3 class runs an RTOS — but both use the same third-party embedded WebRTC library (`libpeer`-class, MIT), differing only in build-time configuration. The PSRAM floor (≥ 4 MB) is the binding constraint that makes encrypted WebRTC media (ICE + DTLS-SRTP + Opus) plausible on the MCU. The public C++ API is identical across both.
- **The "rpi2w" target means the Raspberry Pi Zero 2 W class of Linux single-board computers** (and anything more capable that runs Linux), not a bare-metal MCU. These boards are treated as the lower-risk Linux tier.
- **The "esp32" target means ESP32-S3-class boards with PSRAM**, built via their standard embedded toolchain. Classic ESP32 without PSRAM and 8-bit Arduinos are out of scope (OOS-001).
- **The reference sample's audio backend defaults to a single-header, dependency-free library** (consumer-owned drivers in production), keeping the "builds in minutes" promise; the exact library is a planning decision.
- **The consumer owns microphone, speaker, and UI drivers.** libaivg-sat is a protocol library, not an application framework.
- **Wire parity is validated by running the C++ and TypeScript SDKs against the same gateway and comparing message shapes**; no separate conformance-test framework is required.
- **This feature does not touch `aivg_core`, the management plane, or any agent-platform plugin** — only the C++ SDK, its samples, and its docs. The Python test suite is unaffected.
- **The frozen wire contract this SDK consumes is whatever the gateway currently advertises** (the post-018 reset value at time of writing); the SDK keys off the major version for compatibility rather than a hard-coded string.

## Dependencies

- **Prior features**:
  - The contract that froze the satellite-side WebSocket + REST + WebRTC surface (feature 011), as currently reset by feature 018.
  - The TypeScript SDK `@aivg/sat-sdk` (feature 014) as the byte-shape reference for the public API and event payloads.
  - The agent-platform-agnostic voice loop (feature 015), so a device built on this SDK works against any agent-platform-backed gateway without SDK changes.
  - Supersedes the unmerged `016-cpp-sdk` draft, inheriting its public-API design while committing the transport (WebRTC) and target-floor (PSRAM-class) decisions it left open.
- **Third-party libraries**:
  - A single third-party embedded WebRTC library under a permissive OSI license (MIT/Apache-2.0) serving **both** tiers — reference candidate `libpeer` (MIT), which supports ESP32 and Linux/RPi. Using one library across both tiers maximizes shared transport code behind the common API. (Final pinning/version is a planning decision; the license + cross-tier-support constraints are fixed per the 2026-05-22 clarification.)
  - A header-only JSON library and a small WebSocket client for the management plane.
  - Excluded: Espressif's `esp-adf-libs`-based WebRTC solution (product-locked "Espressif Modified MIT" license — see FR-018).
