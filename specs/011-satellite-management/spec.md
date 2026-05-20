# Feature Specification: Satellite Management — Onboard, Configure & OTA

**Feature Branch**: `011-satellite-management`
**Created**: 2026-05-19
**Status**: Draft
**Input**: User description: "satellite management - onboard, configure and ota
updates with ui (refer this for design /Users/ys/coderepo/infinilake/ui)"

## Overview

Hermes can already carry a voice turn for a connected satellite, but there is
no way for an operator to **bring a new satellite into the fleet, see and tune
the fleet, or move it to new firmware**. Today a device is only usable if it
was hand-provisioned and hand-registered; configuration is whatever shipped
defaults the device booted with; and there is no supervised path to update
firmware.

This feature delivers the **satellite management plane** and its operator
surfaces. The **two required primary surfaces** are:

1. **A management CLI** — a new, separate binary (distinct from the existing
   `hermes` CLI; it is *not* a subcommand of Hermes) that operates the
   management plane from the terminal: list, onboard, configure, command, OTA,
   with `watch`/`follow` modes for live fleet/log/OTA streaming. It is
   primarily a **thin translator from CLI calls to REST**, with a small set of
   **local-only operations** for things that cannot be REST — notably
   **Improv-over-BLE provisioning**, which runs locally on the operator's host
   before the REST register call. The CLI is the **canonical integration
   surface** for any agent or script (Hermes's agent skill, other automation)
   and exposes a **stable, documented command/output contract** (including a
   machine-readable/JSON output mode so non-interactive consumers can rely on
   it).
2. **A per-agent-platform skill** — drives onboarding, configuration, OTA,
   and point-in-time status queries conversationally. The skill **invokes the
   management CLI as its single execution surface** rather than duplicating a
   REST client; other agents may do the same. v1 ships a **Hermes agent
   skill**; OpenClaw and future-platform skills are planned and reuse the
   same CLI verbatim. The CLI itself is platform-neutral.

A **web UI dashboard is optional and lower priority** (a single P3 story): if
built, it follows the referenced Hermes design system
(`/Users/ys/coderepo/infinilake/ui` — dark-first, one accent, status-before-
chrome). The feature is complete and shippable with CLI + skill alone; the UI
is not on the critical path.

Operator surfaces connect to the gateway over a **REST API** (the App. A
request/response endpoints). **Streaming (SSE/WebSocket) is retained only for
live log tailing and OTA-progress** consumed by the CLI's follow mode — not as
the operator's general transport. The **gateway↔device always-on control
WebSocket (`WS /satellite/ws`) is unchanged** and remains how devices
register/heartbeat and how config/commands/OTA reach them (constitution III).

The management plane is the App. A surface from
`docs/generic-voice-satellite-design.md` (registry/lifecycle, configuration,
real-time logs, commands, OTA, and the always-on device control WebSocket).
Per the
constitution, the gateway and the management contract are **identical for all
device types** — the only sanctioned per-type divergence is that `browser`
satellites have no OTA and that `echo_strategy` is a per-device enum. STT, TTS,
the agent loop, endpointing, config file, and logs remain Hermes's; this
feature adds transport, registry, and operator surfaces only — it does not
rebuild any of them.

Onboarding model (clarified): a new headless satellite does **not** type its
own Wi-Fi credentials. The operator runs the agent skill / CLI from a BLE-
capable host, which uses **Improv-over-BLE** to hand the device its Wi-Fi
credentials and a best-effort gateway hint. The device then connects, calls
`register`, and appears (via CLI/skill, and the optional UI) as a claimable/
pending device the operator names and confirms. The gateway remains the
source of truth.

## Clarifications

### Session 2026-05-20

- Q: Is the satellite system Hermes-only, or platform-agnostic? → A:
  **Platform-agnostic.** The satellite core (registry, management plane,
  CLI, OTA, control WS) is decoupled from any single agent platform via an
  `AgentPlatform` plugin seam. **Hermes is the v1 canonical platform
  plugin**; OpenClaw is a planned next plugin. This is a constitution
  amendment (v2.0.0 — Principle IV redefined). Mentions of "Hermes" below
  refer to the v1 plugin unless they are about its existing assets
  (config.yaml, providers, logs) which the Hermes plugin reuses unchanged.
- Q: Is the "CLI" the existing Hermes CLI, or a separate one? → A: **A
  separate management CLI**, a new binary distinct from the `hermes` CLI.
  Under v2.0.0 it is platform-neutral: package `sat_cli`, binary `sat-cli`.
- Q: How does the Hermes agent skill reach the management plane? → A: It
  **shells out to the management CLI** as its single integration surface
  (same path other agents/scripts use); the skill does not duplicate a REST
  client.
- Q: Is the management CLI a strict thin REST translator, or does it also
  host local-only operations? → A: **Thin REST translator with local-only
  operations** where required — specifically Improv-over-BLE provisioning
  runs locally on the operator's host *before* the REST register call.
- Q: Is the management CLI a stable, documented integration surface for
  other agents/scripts? → A: **Yes — a stable, documented contract**
  (versioned commands, flags, exit codes) with a non-interactive/JSON
  output mode required for agent consumption.

### Session 2026-05-19

- Q: What is this feature's scope re: the management plane? → A: Build the
  management plane **and** a management CLI **and** a Hermes agent skill to
  operate it; a web UI is optional/lower priority (see below). (See 2026-05-20
  session for the clarification that the CLI is a separate binary, not the
  existing `hermes` CLI.)
- Q: How does onboarding a new satellite work? → A: **Improv-over-BLE**
  provisioning driven by the agent skill + CLI from a BLE-capable host; the
  device then self-registers and is claimed/named via CLI/skill (or the
  optional UI).
- Q: Disposition of the web UI dashboard? → A: CLI + agent skill are the
  required primary surfaces; the web UI is **optional and lower priority** (a
  single P3 story) — the feature ships complete with CLI + skill alone.
- Q: REST vs the design's control WebSocket — what is dropped vs kept? → A:
  Operator surfaces connect over **REST**; SSE/WebSocket is retained **only
  for live log tailing and OTA-progress** in the CLI follow mode. The
  gateway↔device always-on control WebSocket is **unchanged**.
- Q: How is "live" state surfaced without a dashboard? → A: **CLI watch/
  follow** modes (live list, tail logs, OTA progress) plus **on-demand**
  point-in-time queries via the agent skill; no persistent always-updating
  view is required.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See the whole fleet at a glance (Priority: P1)

An operator runs the CLI `list` (or asks the agent skill) and immediately sees
every satellite, its online/offline status, what it is doing right now (idle,
listening, speaking, mic-muted), when it was last seen, and whether its core
services (STT / TTS / wake) are healthy — answering "is the fleet working?" at
a glance, then drills into one device for its full state and a `follow`-mode
tailing log.

**Why this priority**: Visibility is the foundation every other journey builds
on and is independently valuable even with no write actions. It is also the
lowest-risk slice (read-only) and proves the management plane + control
channel end to end.

**Independent Test**: With at least one registered device, run the CLI fleet
list and confirm status/health/last-seen are reported; run the CLI in
`watch`/`follow` mode and confirm a device going offline and a log tail update
without re-invoking the command.

**Acceptance Scenarios**:

1. **Given** three registered satellites (one offline, one mic-muted, one
   idle), **When** the operator runs the CLI fleet list, **Then** each device
   reports its status, a one-line state, last-seen, and STT/TTS/Wake health,
   and the offline device is clearly marked as offline.
2. **Given** the CLI fleet list running in `watch` mode, **When** a device
   goes offline, **Then** the output reflects offline within one heartbeat
   interval without re-invoking the command.
3. **Given** a device's log `follow` is running, **When** the device fires its
   wake word and speaks, **Then** the streamed entries show the
   listening → thinking → speaking progression as it happens.
4. **Given** the agent skill, **When** the operator asks "is the fleet
   healthy?", **Then** the skill returns the current devices, statuses, and
   which device (if any) needs attention.
5. **Given** the optional web UI is built, **When** the operator opens the
   fleet view, **Then** it presents the same data following the referenced
   design system — but the feature is considered complete without it.

---

### User Story 2 - Onboard a new satellite (Priority: P1)

An operator has a new, unconfigured headless satellite (RPi or ESP32). From a
BLE-capable host they invoke the agent skill or CLI onboarding flow, which
finds the device over BLE, sends it the Wi-Fi credentials and an optional
gateway hint via Improv, and waits. The device joins Wi-Fi, registers with the
gateway, and shows up (via CLI/skill) as a **pending/unclaimed** device. The
operator gives it a room name, confirms, and the gateway pushes default
config; the device becomes a normal fleet member.

**Why this priority**: Without onboarding the fleet cannot grow; this is the
headline capability in the request and is independently demonstrable end to
end.

**Independent Test**: Take a factory-state device, run the onboarding skill/CLI
with test Wi-Fi credentials, and confirm the device transitions from "not
present" → "pending/unclaimed" → named fleet member with default config
applied, with no keyboard ever attached to the device.

**Acceptance Scenarios**:

1. **Given** a factory-state device in BLE provisioning range, **When** the
   operator runs the onboarding skill/CLI and supplies SSID + password,
   **Then** the device is sent credentials over Improv-BLE and the flow
   reports provisioning progress and the resolved device endpoint.
2. **Given** a device that finished Improv provisioning, **When** it joins
   Wi-Fi and registers, **Then** it is listed by the CLI/skill as a pending/
   unclaimed device with its hardware id, type, and firmware version.
3. **Given** a pending device, **When** the operator names it and confirms
   adoption via the CLI/skill, **Then** the gateway's default config is
   applied and persisted to the device and the device moves to the normal
   fleet list.
4. **Given** Improv provisioning fails (wrong Wi-Fi password, out of range,
   BLE unsupported on host), **When** the flow times out, **Then** the
   operator sees a specific failure reason and a documented fallback
   (e.g. SoftAP captive portal) and the fleet is left unchanged.
5. **Given** the gateway advertises itself on the LAN, **When** the device
   registers with no gateway hint, **Then** discovery still succeeds (gateway
   hint is best-effort, not required).

---

### User Story 3 - Configure a satellite (Priority: P2)

An operator uses the CLI or the agent skill to change a device's settings —
speaker volume, mic gain, wake word and sensitivity, TTS voice, VAD/tuning,
LED-ring behavior — and the change applies on the device immediately and
persists across reboots. The same configuration is editable from the CLI and
conversationally via the agent skill (and the optional UI), against one shared
config contract.

**Why this priority**: Tuning is the day-to-day reason an operator returns to
the tool, but it depends on a registered device (US1/US2) existing first.

**Independent Test**: Change a setting (e.g. wake sensitivity) from each
surface, confirm the running device reflects it within seconds, then reboot
the device and confirm the setting survived.

**Acceptance Scenarios**:

1. **Given** an online device, **When** the operator changes speaker volume
   via the CLI or skill, **Then** the device's playback volume changes within
   a few seconds and the new value is reported as the running value.
2. **Given** a changed config, **When** the device reboots, **Then** it comes
   back with the changed config, not factory defaults.
3. **Given** an offline device, **When** the operator submits a config change,
   **Then** the operator is told the device is offline and the change is
   either safely queued for reconnect or rejected — never silently lost.
4. **Given** the device exposes a config schema, **When** any surface
   presents editable settings (CLI options, skill, or optional UI form),
   **Then** the fields, ranges, and options come from that schema (the gateway
   does not branch by device type).
5. **Given** the agent skill, **When** the operator says "set the kitchen
   satellite wake word to hey jarvis", **Then** the same config path applies
   and confirms the change.

---

### User Story 4 - Update firmware over the air (Priority: P2)

An operator checks whether a device (or the fleet) has a firmware update,
reviews the version and changelog, applies it, and watches supervised progress
through download → flash → reboot → re-register, with a safe outcome on
failure (rollback for partitioned devices). Browser satellites are explicitly
not OTA-eligible and are shown as such.

**Why this priority**: Keeping the fleet current matters but is lower-frequency
than configuration and must not be attempted before fleet/visibility exist.

**Independent Test**: With a device on an older firmware version, run an OTA
check, see the available version + changelog, apply it, and observe progress
states to a successful re-register on the new version — and separately, force
a failed flash and confirm the device returns to a working state.

**Acceptance Scenarios**:

1. **Given** an online OTA-eligible device on an older version, **When** the
   operator runs an update check via CLI/skill, **Then** it reports
   update-available, the latest version, and a changelog reference.
2. **Given** an available update, **When** the operator applies it, **Then**
   the device reports staged progress (downloading → flashing → rebooting) and
   the CLI `follow` mode reflects each state live.
3. **Given** an OTA that fails to flash or boot, **When** the failure is
   detected, **Then** the device returns to its previous working firmware
   (rollback where the device supports it) and the failure is surfaced with a
   reason; the device does not end up bricked or stuck offline.
4. **Given** a browser satellite, **When** the operator inspects it, **Then**
   OTA actions are reported as not applicable (only sanctioned per-type
   divergence).
5. **Given** an offline device, **When** an update is requested, **Then** the
   action is unavailable until the device is back online.

---

### User Story 5 - Operate and diagnose a device (Priority: P3)

An operator needs to act on a device without onboarding or reconfiguring it:
reboot it, restart its voice or manager process, mute/unmute the mic, flash its
LED to physically identify it, reset its config, factory-reset it, or unpair
(remove) it from the fleet — each with a clear confirmation for destructive
actions — and watch the live log to diagnose a misbehaving device.

**Why this priority**: Important for operations but every action here is a
refinement on top of an existing, visible, registered device.

**Independent Test**: Trigger a non-destructive command (identify-LED) and a
destructive one (factory reset, with confirmation) and confirm the device acts
and the fleet/registry reflect the outcome.

**Acceptance Scenarios**:

1. **Given** an online device, **When** the operator triggers "identify LED",
   **Then** that physical device's LED indicates and the action is logged.
2. **Given** a misbehaving device, **When** the operator runs the CLI log
   `follow` filtered by source (e.g. wake / asr / webrtc), **Then** matching
   entries stream live.
3. **Given** a destructive action (factory reset / unpair), **When** the
   operator selects it, **Then** an explicit confirmation is required before
   it executes, and afterward the fleet state reflects the result (e.g. the
   device leaves the registry and may re-register).
4. **Given** the fleet is at its device limit, **When** the operator tries to
   add another, **Then** the CLI/skill refuses with a clear reason and a
   pointer to unpair one first.

---

### Edge Cases

- **Device offline during a write**: config change, command, or OTA submitted
  to an offline device must be clearly refused or safely queued — never
  silently dropped.
- **Improv/BLE unavailable**: host lacks BLE, or the device is out of range,
  or the wrong Wi-Fi password is given → onboarding fails with a specific
  reason and the documented SoftAP/captive-portal fallback is offered.
- **Gateway not discoverable**: mDNS/DNS-SD blocked (VLAN/AP isolation) →
  onboarding still completes when a manual gateway hint is supplied.
- **Unclaimed device never named**: a registered-but-unadopted device must
  remain visible as pending and not silently disappear or auto-adopt.
- **OTA failure / power loss mid-flash**: device must recover to a working
  firmware and re-register; the operator must be able to see it did.
- **Re-register after factory reset**: a reset device returns to the
  pending/unclaimed state rather than reappearing with stale prior config.
- **Concurrent edits**: two operators (UI + CLI/skill) changing the same
  device's config must not corrupt config; last write is applied predictably
  and the other surface reflects the new running value.
- **Stale view**: the displayed running config/state must converge to the
  device's actual state within a heartbeat, not show indefinitely stale data.
- **Device-type neutrality**: the gateway/registry/dashboard must not branch
  behavior by `device_type` except the two sanctioned divergences (browser =
  no OTA; `echo_strategy` enum).

## Requirements *(mandatory)*

### Functional Requirements

**Management plane & registry**

- **FR-001**: The system MUST maintain a registry of satellites, each with a
  stable device id, device type, status (online/offline/connecting/error),
  last-seen, firmware version, and current routing/connection/health summary.
- **FR-002**: The system MUST provide an always-on control channel per device,
  independent of any active voice call, so registration, heartbeat, config
  push, commands, logs, and OTA progress work even when no call is active.
- **FR-003**: A device MUST be able to register with the gateway on boot and
  receive a session identity, the authoritative management endpoint, and the
  gateway's default configuration.
- **FR-004**: The system MUST reuse Hermes's existing configuration file,
  secrets, provider abstractions, endpointing, and log destination; it MUST
  NOT introduce a separate STT/TTS engine, config loader, or secret store.
- **FR-005**: The management contract and gateway behavior MUST be identical
  across device types; the only permitted per-type divergence is browser =
  no OTA and the per-device `echo_strategy` value.

**Operator surfaces (UI, CLI, agent skill)**

- **FR-006**: The system MUST provide a **management CLI** — a new, separate
  binary distinct from the existing `hermes` CLI — that performs fleet list,
  device onboarding, configuration, commands, and OTA against the management
  plane, suitable for headless and scripted use, including `watch`/`follow`
  modes for live fleet, log, and OTA-progress streaming. The CLI MUST be
  primarily a thin translator from CLI calls to the REST API and MUST also
  host the small set of local-only operations that cannot be REST —
  specifically Improv-over-BLE provisioning, executed on the operator's host
  before the REST register call. The CLI MUST expose a **stable, documented
  contract** (versioned commands/flags/exit codes) and a non-interactive
  machine-readable (JSON) output mode suitable for consumption by agents and
  scripts.
- **FR-007**: The system MUST provide a Hermes agent skill that lets an
  operator perform onboarding, configuration, OTA, and point-in-time status
  queries conversationally. The skill MUST invoke the management CLI as its
  single execution surface (it MUST NOT duplicate a REST client of its own),
  so any agent that can run the CLI gets the same capabilities Hermes does.
- **FR-008**: Operator surfaces MUST connect to the gateway over a REST API
  (App. A request/response endpoints); streaming (SSE/WebSocket) MUST be used
  only for live log tailing and OTA-progress in the CLI follow mode, not as
  the operator's general transport. The gateway↔device always-on control
  WebSocket MUST remain unchanged (constitution III). Every operator surface
  (CLI, agent skill, optional UI) MUST operate the same management plane and
  configuration contract, and an action on one MUST be reflected in the
  others.
- **FR-009**: The system SHOULD optionally provide a web UI (a single P3
  story) presenting the same fleet/device data and actions; if built it MUST
  follow the referenced Hermes design system (dark-first, single accent,
  status-before-chrome, sentence case, documented primitives). The feature is
  complete and shippable without the UI; the UI is not on the critical path.

**Onboarding**

- **FR-010**: The system MUST onboard a new headless satellite by delivering
  Wi-Fi credentials and an optional best-effort gateway hint to the device via
  **Improv-over-BLE executed locally by the management CLI on the operator's
  BLE-capable host**, without any keyboard/display attached to the device.
  After successful provisioning, the CLI MUST continue the onboarding via the
  REST API (claim/adopt + default-config push).
- **FR-011**: After provisioning, a device that registers but has not been
  adopted MUST appear as a pending/unclaimed device that the operator can name
  and confirm; on confirmation the gateway's default config MUST be applied
  and persisted to the device.
- **FR-012**: Onboarding MUST surface progress and, on failure, a specific
  reason and a documented fallback path (SoftAP/captive portal), leaving the
  fleet unchanged on failure.
- **FR-013**: Gateway discovery MUST succeed without a manual hint when the
  gateway is discoverable on the LAN, and MUST still succeed with a manual
  hint when LAN discovery is blocked.

**Configuration**

- **FR-014**: Operators MUST be able to view a device's running configuration
  and change settings including at least: speaker volume, mic gain, wake word
  and sensitivity, TTS voice, VAD/tuning parameters, and LED-ring behavior.
- **FR-015**: A configuration change to an online device MUST apply on the
  device within seconds and MUST persist across device reboots.
- **FR-016**: A configuration change targeting an offline device MUST be
  explicitly refused or safely queued for reconnect — never silently lost.
- **FR-017**: Editable settings on every surface (CLI options/help, agent
  skill, optional UI form) MUST be driven by the device-provided config
  schema rather than hard-coded per device type.

**Commands & diagnostics**

- **FR-018**: Operators MUST be able to issue device commands at least:
  reboot, restart voice, restart manager, reset config, factory reset, mute/
  unmute mic, and identify (LED), with the device acknowledging acceptance.
- **FR-019**: Destructive actions (factory reset, unpair/remove) MUST require
  explicit operator confirmation before executing.
- **FR-020**: Operators MUST be able to view a live, filterable log stream per
  device (filter by level and by source such as wake/asr/tts/webrtc/system/
  ota) and an aggregate fleet log.
- **FR-021**: A device MUST be removable from the fleet, after which it may
  re-register as a new pending device.

**OTA**

- **FR-022**: Operators MUST be able to check whether a device has a firmware
  update and see the latest version and a changelog reference.
- **FR-023**: Operators MUST be able to apply an update and observe supervised
  staged progress (checking → downloading → flashing → rebooting → re-
  registered) reflected live across surfaces.
- **FR-024**: A failed or interrupted update MUST leave the device on a
  working firmware (rollback where the device supports it) and surface the
  failure with a reason; the device MUST NOT be left bricked or indefinitely
  offline by a failed update.
- **FR-025**: Browser satellites MUST be presented as not OTA-eligible (the
  one sanctioned per-type divergence), and OTA actions MUST be unavailable for
  offline devices.

**Liveness & integrity**

- **FR-026**: The CLI `watch`/`follow` modes MUST reflect status, state,
  running-config, and OTA-progress changes within one heartbeat interval
  without re-invocation; the agent skill MUST return current state on demand.
  A persistent always-updating view is NOT required (no dashboard on the
  critical path).
- **FR-027**: Concurrent configuration writes from different surfaces MUST NOT
  corrupt a device's configuration; the applied result MUST be deterministic
  and converge across surfaces.

### Key Entities

- **Satellite (device)**: a registered voice endpoint. Key attributes: device
  id, device type, status, last-seen, IP, firmware version, connection type,
  health summary (STT/TTS/wake), `echo_strategy`, OTA state. Lifecycle:
  pending/unclaimed → adopted → online/offline → removed.
- **Satellite configuration**: the device's tunable settings (wake word and
  engine, VAD/tuning, input/output volume, mic gain, TTS voice, routing mode,
  LED-ring behavior, log level, heartbeat interval), with a device-provided
  schema; has a running value and a persisted value.
- **Onboarding session**: a transient provisioning attempt for one new device
  (Wi-Fi credentials + optional gateway hint delivered via Improv-BLE) with
  progress and a terminal success/failure reason.
- **Firmware update / OTA job**: an available or in-progress version change
  for one device — target version, changelog reference, staged progress, and
  terminal result (success / rolled-back / failed).
- **Log entry**: a timestamped, leveled, sourced message emitted by a device
  (sources: wake/asr/tts/webrtc/system/ota), streamed live and filterable.
- **Fleet**: the collection of registered satellites, with an enforced device
  limit and aggregate health.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can take a factory-state headless device to a named,
  default-configured fleet member in under 5 minutes, with no keyboard or
  display ever attached to the device.
- **SC-002**: 100% of onboarding attempts end in either an adopted device or a
  specific, actionable failure reason — none end ambiguously or silently.
- **SC-003**: A configuration change applied from any surface is reflected on
  an online device within 5 seconds and survives a device reboot in 100% of
  attempts.
- **SC-004**: The CLI `watch`/`follow` modes reflect a device going offline,
  changing state, or finishing an OTA within one heartbeat interval without
  re-invocation; an on-demand skill query returns the current state.
- **SC-005**: 100% of OTA failures (including simulated power loss mid-flash)
  leave the device on a working, re-registering firmware — zero bricked or
  indefinitely-offline devices.
- **SC-006**: The same management actions (list, configure, command, OTA) are
  achievable from both required surfaces (management CLI, agent skill that
  invokes the CLI) — and the optional UI if built — and produce the same
  observable result. A non-Hermes agent or script that can execute the
  management CLI's documented commands MUST be able to reproduce every
  management action with no additional integration code, using the CLI's
  machine-readable output.
- **SC-007**: An operator can correctly answer "is the fleet healthy, and
  which device needs attention?" within 5 seconds of reading a single CLI
  fleet-list output (or one skill reply) — status is legible at a glance
  without scrolling secondary detail.
- **SC-008**: Every destructive action requires confirmation; zero
  destructive actions execute without it.
- **SC-009**: No gateway/registry/dashboard behavior branches on device type
  except the two sanctioned divergences (browser = no OTA; `echo_strategy`).

## Assumptions

- Single-tenant, trusted-LAN operator usage; per-device auth and TLS are
  explicitly deferred (constitution: security deferred until non-LAN
  deployment) and out of scope for this feature.
- The referenced design at `/Users/ys/coderepo/infinilake/ui` is the
  authoritative visual/UX reference **only for the optional web UI** (P3); it
  is not on this feature's critical path. CLI ergonomics and the agent skill
  are the required experience and are not bound by that visual design system.
- Operator↔gateway transport is REST; SSE/WebSocket is used only for live log
  tailing and OTA-progress in the CLI follow mode. The gateway↔device
  always-on control WebSocket from prior design is reused unchanged.
- Device-side provisioning transports (Improv-BLE responder on the device,
  SoftAP captive-portal fallback, pre-baked image path) exist or are provided
  by the device firmware; this feature drives them from the host, it does not
  re-implement device firmware.
- STT/TTS/agent/endpointing/config-file/logs belong to the **active agent
  platform** (the v1 Hermes plugin reuses `~/.hermes/config.yaml`, Hermes's
  providers, and `~/.hermes/logs/gateway.log` verbatim — constitution IV).
  This feature is the management/transport/registry + operator-surface
  layer; it does not rebuild any platform primitive and does not assume a
  single platform — the `AgentPlatform` plugin seam picks which.
- OTA applicability follows the design: partitioned devices (ESP32) support
  A/B rollback, RPi uses download + service restart, browser has no OTA.
- The fleet has an enforced device limit (the referenced list mockup shows a
  "10 / 10, limit reached" state); the exact number is a configurable gateway
  setting and not fixed by this spec.
- A BLE-capable host is available to the operator for the Improv onboarding
  path; the management CLI runs on this host and is the component that drives
  Improv-over-BLE locally before completing onboarding via REST. Headless
  devices themselves are not assumed BLE-provisionable without such a host.
- "Live" means within the configured heartbeat interval (design default 30 s),
  not literally instantaneous, unless an action provides its own progress
  stream (OTA, onboarding).

## Dependencies

- The active agent platform's gateway, config file, secrets, log destination,
  and STT/TTS/agent/endpointing provider layer (reused, not rebuilt). For
  v1: Hermes (`~/.hermes/config.yaml`, `~/.hermes/.env`, Hermes providers,
  `~/.hermes/logs/gateway.log`).
- The satellite WebRTC/voice adapter from prior features (the voice plane is
  out of scope here; this feature is the control/management plane beside it).
- Device firmware that implements the generic four-plane contract, an Improv-
  BLE provisioning responder, a config schema, and (for non-browser) an OTA
  responder.
- A LAN with optional mDNS/DNS-SD for zero-config gateway discovery.
