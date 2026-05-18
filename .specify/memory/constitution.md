<!--
SYNC IMPACT REPORT
==================
Version change: (template / unversioned) → 1.0.0
Bump rationale: Initial ratification of the project constitution from the
  generic-voice-satellite design (docs/generic-voice-satellite-design.md).
  First concrete version, so MAJOR baseline 1.0.0.

Principles defined (all new):
  - I. Thin Satellite, Gateway-Owned Intelligence (NON-NEGOTIABLE)
  - II. Generic Four-Plane Contract
  - III. Separate Control and Voice Connections
  - IV. Reuse Hermes, Don't Rebuild
  - V. Research-Backed, Constraint-Driven Decisions

Added sections:
  - Hardware & Platform Constraints (was [SECTION_2_NAME])
  - Development Workflow & Quality Gates (was [SECTION_3_NAME])
  - Governance

Removed sections: none (template placeholders fully replaced).

Templates / artifacts status:
  - .specify/templates/plan-template.md ✅ aligned (Constitution Check gate
    references the constitution file generically; no hardcoded principles to
    update)
  - .specify/templates/spec-template.md ✅ aligned (no constitution-specific
    bindings)
  - .specify/templates/tasks-template.md ✅ aligned (no constitution-specific
    bindings)
  - .specify/templates/checklist-template.md ✅ aligned (generic)
  - README.md / docs/quickstart.md / commands dir ⚠ not present (nothing to
    propagate)

Follow-up TODOs: none. RATIFICATION_DATE set to adoption date 2026-05-18
  (initial adoption coincides with this constitution's creation).
-->

# Hermes Voice Satellite Constitution

## Core Principles

### I. Thin Satellite, Gateway-Owned Intelligence (NON-NEGOTIABLE)

A satellite captures audio, decides *when* to stream it (VAD/wake word),
transports it, and plays back what returns. It MUST NOT perform ASR, TTS, the
agent loop, or authoritative end-of-utterance detection. All speech
recognition, synthesis, agent reasoning, and silence/endpointing run on the
Hermes gateway through its existing pluggable provider layer.

Rules:

- A satellite or the WebRTC adapter MUST NOT instantiate Whisper, Piper, or
  any STT/TTS engine directly. STT/TTS MUST be reached only through Hermes's
  configured provider interfaces, so satellites inherit the gateway's provider
  choice and fallbacks.
- Device-side VAD/wake word MAY *gate* the upstream stream to save bandwidth,
  but the authoritative end-of-utterance is Hermes's existing server-side
  silence algorithm, reused unchanged.
- Piper is not a Hermes engine and MUST NOT be introduced.

Rationale: This is forced by the most constrained target (RPi Zero 2 W,
512 MB / 1 GHz) and it makes every satellite inherit Hermes's STT/TTS
capabilities for free. Violating it duplicates intelligence, fragments
configuration, and breaks the constrained device.

### II. Generic Four-Plane Contract

Every satellite, regardless of hardware, MUST implement the same four logical
planes with identical semantics: control plane, voice plane, capture/
endpointing plane, and playback plane. Device-specific sections only define
*how* each plane is realized — never *what* it means to the gateway.

Rules:

- The shared data models `SatelliteState`, `SatelliteConfig`, and `LogEntry`
  (Appendix B of the design) MUST be used unchanged across all device types.
- The only sanctioned per-type divergence is: `browser` has no OTA, and the
  echo-handling strategy is an explicit enum
  (`hardware_xmos | software_speex | half_duplex | browser_aec3`) rather than a
  single global ducking approach. Any new per-type divergence MUST be added to
  the contract first, not improvised per device.
- The gateway MUST remain identical for all device types; protocol-branching
  by `device_type` in the gateway registry/dashboard is prohibited.

Rationale: A single contract is what makes the design "generic"; per-device
special cases in the gateway are the failure mode this principle prevents.

### III. Separate Control and Voice Connections

Each satellite maintains exactly two connections: an always-on control-plane
WebSocket (`WS /satellite/ws`) and a per-session WebRTC voice connection.

Rules:

- The control plane MUST stay available when there is no active call
  (register, heartbeat, config push, commands, logs, OTA, online/offline).
- Durable control traffic MUST NOT be multiplexed into a WebRTC data channel,
  because a data channel only exists while a PeerConnection is up.
- A single SCTP datachannel on the voice PeerConnection is permitted ONLY for
  call-scoped, low-latency UI events (partial transcripts, listening/speaking
  state, barge-in). Everything durable stays on the WS.
- The satellite is the WebRTC offerer for all device types. ICE uses full
  gather-then-offer; `/webrtc/candidate` is kept only as a fallback.

Rationale: Coupling control availability to call state breaks online/offline
tracking, config push, and "start a call" — wrong for a satellite.

### IV. Reuse Hermes, Don't Rebuild

The satellite system is a new platform adapter that plugs into the existing
Hermes gateway exactly like the Telegram and Discord adapters — not a
standalone pipeline or separate daemon.

Rules:

- The adapter MUST reuse Hermes's existing assets and MUST NOT rebuild them:
  gateway lifecycle, `~/.hermes/config.yaml` loader, `~/.hermes/.env` secrets,
  STT/TTS provider abstractions, the server-side silence algorithm, and
  `~/.hermes/logs/gateway.log`.
- New configuration MUST be added as a `satellite:` / `webrtc:` block in the
  existing `~/.hermes/config.yaml`; no new secret store and no new config
  loader.
- The adapter is a thin transport + registry layer only; STT, the agent loop,
  TTS, and endpointing are invoked through Hermes's provider interfaces.

Rationale: Reusing Hermes's provider layer, config, and endpointing is the
entire integration strategy; reimplementing any of it forks behavior and
maintenance.

### V. Research-Backed, Constraint-Driven Decisions

Hardware and platform decisions MUST be justified by researched device
constraints, not preference, and MUST be validated before they are relied on.

Rules:

- Every design decision that depends on device limits (RAM, CPU cores, codec
  revision, AEC availability, I2S role, supported sample rates) MUST cite the
  binding constraint that forces it.
- Heavy-pipeline targets MUST be load-tested with the full pipeline running
  together (wake word + VAD + AEC + Opus + ICE/SRTP + OS), not component-by-
  component, before the decision is treated as proven.
- Hardware revision / firmware variant MUST be physically confirmed before
  building an OS or firmware image (e.g. ReSpeaker HAT codec revision;
  XVF3800 I2S-master 48 kHz vs 16 kHz build).

Rationale: The constrained targets fail precisely when components that look
fine in isolation contend in practice; unverified assumptions about hardware
have already been the documented failure mode.

## Hardware & Platform Constraints

The three supported satellites and their binding constraints:

- **RPi Zero 2 W + ReSpeaker 2-Mic HAT** — 512 MB RAM / 4×1 GHz, no hardware
  AEC, codec varies by board revision. ASR/TTS remote (non-negotiable).
  64-bit Pi OS Lite headless only. Echo: SpeexDSP AEC + half-duplex fallback.
  WebRTC: start with aiortc, migration path to GStreamer `webrtcbin`.
- **ReSpeaker XVF3800 + XIAO ESP32S3** — XMOS does AEC/beamform/NS/AGC/VAD in
  hardware. I2S 48 kHz master firmware variant only; ESP32 is I2S slave.
  No acoustic ducking — the far-end fed to the XMOS *is* the AEC reference.
  `esp_peer` WebRTC; dual-partition A/B OTA.
- **JS / Electron desktop app** — Chromium AEC3 handles echo entirely;
  TTS MUST play through an `<audio>` element in the same renderer. No
  server-side echo handling, no ducking. Push-to-talk v1, openWakeWord v2.
  No OTA.

`echo_strategy` is a per-device enum, never a single global ducking
assumption. Security (per-device auth, TLS) is explicitly deferred for now and
MUST be revisited before any non-LAN deployment.

## Development Workflow & Quality Gates

Build order is mandatory and risk-ordered:

1. Gateway WebRTC adapter + browser satellite first (lowest risk, AEC3 free,
   no hardware/flashing) — proves the aiortc offer/answer + Opus path into
   Hermes's STT/TTS layer.
2. ESP32 satellite — validate I2S firmware master/slave role early; AEC is
   hardware-solved once reference routing is correct.
3. RPi satellite last — requires the full-pipeline load test and a possible
   aiortc → `webrtcbin` migration; confirm HAT revision up front.

Quality gates:

- Each milestone MUST prove an end-to-end loop before the next begins.
- The RPi pipeline MUST pass a combined-load test before being declared
  viable.
- Any deviation from the design's stated decisions MUST be recorded with the
  constraint or evidence that justifies it.

## Governance

This constitution supersedes ad-hoc practices for the Hermes voice satellite
system. The authoritative design source is
`docs/generic-voice-satellite-design.md`; this constitution distills its
non-negotiable rules and takes precedence where the two conflict on principle.

Amendment procedure:

- Amendments MUST be documented in the Sync Impact Report at the top of this
  file, with a version bump and rationale.
- Versioning policy (semantic): MAJOR for backward-incompatible
  principle removals or redefinitions; MINOR for a new principle or materially
  expanded section; PATCH for clarifications and non-semantic refinements.
- Dependent Spec Kit templates (`plan`, `spec`, `tasks`, `checklist`) MUST be
  re-checked for alignment whenever a principle is added, removed, or redefined.

Compliance review:

- Specs, plans, and task sets MUST pass the plan template's Constitution Check
  against these principles before implementation.
- Complexity or any departure from a principle MUST be explicitly justified
  against the binding constraint that requires it; unjustified violations
  block the change.

**Version**: 1.0.0 | **Ratified**: 2026-05-18 | **Last Amended**: 2026-05-18
