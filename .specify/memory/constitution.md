<!--
SYNC IMPACT REPORT
==================
Version change: 2.0.0 → 2.0.1
Bump rationale: PATCH. Branding rebrand only — the product is renamed
  from "Hermes Voice" to AIVG (AI Voice Gateway). Hermes remains the v1
  agent-platform plugin per v2.0.0 Principle IV. No principle text gains
  or loses normative meaning; verified by
  tests/unit/test_constitution_principles_byte_equiv.py (feature 012
  T034).

Modified text:
  - Title: "Hermes Voice Satellite Constitution" → "AIVG Constitution".
  - Project-codename preface: now AIVG-first, with "Formerly 'Hermes
    Voice' through feature 011" as historical context.
  - Governance section: "Hermes Voice satellite system" → "AIVG
    satellite system".
  - Body prose: every product-name mention rewritten to AIVG; every
    Hermes-as-plugin mention preserved verbatim.

Templates / artifacts status:
  - All Spec Kit templates ✅ unchanged (constitution-check text is
    generic).
  - feature 012 plan / research / data-model / contracts ✅ aligned
    in lockstep with this amendment.
  - The compat shims at `src/satellite_core/`, `src/sat_cli/`, and
    `src/hermes_satellite_adapter/` remain for one release with their
    own DeprecationWarnings.

Follow-up TODOs: none. Compat-shim removal tracked in feature 012
  T043 (`specs/012-aivg-branding/followup-shim-removal.md`).

------------------------------------------------------------------
SYNC IMPACT REPORT (previous)
==================
Version change: 1.0.0 → 2.0.0
Bump rationale: MAJOR. Principle IV is **redefined** from a Hermes-specific
  "Reuse Hermes, Don't Rebuild" rule to a platform-neutral "Reuse the
  Upstream Agent Platform, Don't Rebuild Its Primitives" rule. The satellite
  system is now explicitly **agent-platform-agnostic**: Hermes is the v1
  canonical plugin; other platforms (OpenClaw, future) plug in through a
  documented `AgentPlatform` seam. Existing constraints stay; the principle's
  binding text is broadened, which is backward-incompatible at the rule
  level.

Modified principles:
  - IV. Reuse Hermes, Don't Rebuild
       → IV. Reuse the Upstream Agent Platform, Don't Rebuild Its Primitives
  Other principles (I, II, III, V): unchanged in intent; minor wording
  refresh where they referenced Hermes by name.

Added sections: none. (Plugin seam is encoded inside Principle IV; the
  Hardware & Platform Constraints and Development Workflow sections are
  refreshed but not added.)

Removed sections: none.

Templates / artifacts status:
  - .specify/templates/plan-template.md ✅ aligned (Constitution Check is
    generic; no hardcoded Hermes naming to update)
  - .specify/templates/spec-template.md ✅ aligned
  - .specify/templates/tasks-template.md ✅ aligned
  - .specify/templates/checklist-template.md ✅ aligned
  - docs/generic-voice-satellite-design.md ⚠ documents Hermes integration
    specifically; under v2.0.0 it represents the Hermes *plugin*, not the
    whole adapter — note added at top of the satellite spec (feature 011).
  - feature 011 plan/research/data-model/contracts ✅ updated in lock-step
    with this amendment (rename `hermes_satellite_adapter` → `satellite_core`;
    introduce `satellite_core/platforms/hermes/`).
  - Prior features 001–010 use Hermes-only naming; their READMEs are
    grandfathered (they shipped before v2.0.0). Future work tracked as
    follow-up; no rename forced retroactively.

Follow-up TODOs:
  - TODO(rename-existing-package): rename Python package
    `hermes_satellite_adapter` → `satellite_core` and move Hermes-specific
    code to `satellite_core/platforms/hermes/` (executed in feature 011
    tasks).
  - TODO(openclaw-plugin): sketch a `satellite_core/platforms/openclaw/`
    skeleton in a follow-up feature; not part of 011's shipping scope.
-->

# AIVG Constitution

*Project codename: **AIVG (AI Voice Gateway)**. Formerly "Hermes Voice"
through feature 011; renamed in feature 012. The satellite system is
**agent-platform-agnostic** (v2.0.0): Hermes is the v1 canonical
plugin; other agent platforms plug in through Principle IV's seam.*

## Core Principles

### I. Thin Satellite, Gateway-Owned Intelligence (NON-NEGOTIABLE)

A satellite captures audio, decides *when* to stream it (VAD/wake word),
transports it, and plays back what returns. It MUST NOT perform ASR, TTS, the
agent loop, or authoritative end-of-utterance detection. All speech
recognition, synthesis, agent reasoning, and silence/endpointing run on the
gateway through whichever **agent platform** is plugged in (Principle IV).

Rules:

- A satellite or the WebRTC adapter MUST NOT instantiate Whisper, Piper, or
  any STT/TTS engine directly. STT/TTS MUST be reached only through the
  active agent platform's provider interfaces, so satellites inherit that
  platform's provider choice and fallbacks.
- Device-side VAD/wake word MAY *gate* the upstream stream to save bandwidth,
  but the authoritative end-of-utterance is the platform's existing server-
  side silence algorithm, reused unchanged.
- Piper is not a supported gateway engine and MUST NOT be introduced.

Rationale: This is forced by the most constrained target (RPi Zero 2 W,
512 MB / 1 GHz) and it makes every satellite inherit the configured agent
platform's STT/TTS capabilities for free. Violating it duplicates
intelligence, fragments configuration, and breaks the constrained device.

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
- The same neutrality applies across **agent platforms** (Principle IV): the
  registry / management plane / control WS / OTA flow MUST NOT branch on
  *which* agent platform is plugged in. Per-platform divergence belongs
  inside the platform plugin, behind the `AgentPlatform` interface.

Rationale: A single contract is what makes the design "generic"; per-device
*and* per-platform special cases in the gateway are the failure mode this
principle prevents.

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
- Operator surfaces (CLI, agent-platform skill, optional UI) use a **REST
  API** for actions; SSE/WebSocket is permitted **only** for live log
  tailing and OTA-progress streaming consumed by the CLI's follow mode.

Rationale: Coupling control availability to call state breaks online/offline
tracking, config push, and "start a call" — wrong for a satellite.

### IV. Reuse the Upstream Agent Platform, Don't Rebuild Its Primitives

The satellite system is **agent-platform-agnostic**. It plugs into one of
several supported upstream agent platforms (v1: Hermes; planned: OpenClaw;
future: others) through a documented `AgentPlatform` interface. The satellite
core MUST NOT reimplement what an agent platform already owns: STT, TTS, the
agent loop, server-side endpointing, the platform's config file, or its
secrets store.

Rules:

- A platform plugin lives in `satellite_core/platforms/<platform_name>/` and
  implements a documented `AgentPlatform` interface that exposes at least:
  `transcribe(audio) → text`, `agent_step(text, session) → reply_stream`,
  `synthesize(text) → audio`, and `endpoint(audio_frame) → end_of_utterance?`.
  Adding a new platform MUST NOT require changes anywhere else in the
  satellite core.
- Each platform plugin MUST reuse that platform's existing assets unchanged:
  its gateway lifecycle (where applicable), its config file and secrets, its
  STT/TTS provider abstractions, its server-side silence algorithm, and its
  log destination. New satellite-side configuration goes in the satellite
  system's own config block, never inside the upstream platform's config.
- The Hermes plugin (v1 canonical) consumes `~/.hermes/config.yaml`,
  `~/.hermes/.env`, Hermes's STT/TTS providers, Hermes's silence algorithm,
  and `~/.hermes/logs/gateway.log` — verbatim, no replacement.
- The satellite adapter is a thin transport + registry + management layer
  only; STT, the agent loop, TTS, and endpointing are invoked through the
  active platform plugin's `AgentPlatform` implementation.
- Operator surfaces (CLI, skills) are platform-agnostic and MUST NOT
  hard-depend on any one platform. A per-platform agent skill (e.g. a Hermes
  agent skill) MAY ship alongside its platform plugin but MUST invoke the
  satellite CLI as its execution surface, not the platform's internals.

Rationale: Reusing each platform's provider layer, config, and endpointing
is the integration strategy; reimplementing any of it forks behavior and
maintenance. Hard-wiring the satellite to a single platform locks the system
to that platform's future — the project's stated goal is multi-platform
support, so the plugin seam is the binding constraint that makes that
possible.

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
- Each new agent platform plugin MUST be exercised against the same
  end-to-end voice loop the Hermes plugin passes, not just unit-tested in
  isolation, before it is treated as supported.

Rationale: The constrained targets fail precisely when components that look
fine in isolation contend in practice; unverified assumptions about hardware
have already been the documented failure mode. The same logic extends to a
new platform plugin: it is "supported" only when proven end-to-end.

## Hardware & Platform Constraints

The three supported satellites and their binding constraints (independent of
which agent platform is plugged in upstream):

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
   the active agent platform's STT/TTS layer.
2. ESP32 satellite — validate I2S firmware master/slave role early; AEC is
   hardware-solved once reference routing is correct.
3. RPi satellite last — requires the full-pipeline load test and a possible
   aiortc → `webrtcbin` migration; confirm HAT revision up front.

Quality gates:

- Each milestone MUST prove an end-to-end loop before the next begins.
- The RPi pipeline MUST pass a combined-load test before being declared
  viable.
- Each new agent platform plugin MUST pass the same end-to-end voice loop
  the Hermes plugin passes before being declared supported (Principle V).
- Any deviation from the design's stated decisions MUST be recorded with the
  constraint or evidence that justifies it.

## Governance

This constitution supersedes ad-hoc practices for the AIVG satellite
system. The authoritative design source is
`docs/generic-voice-satellite-design.md`; under v2.0.0 that document
describes the **Hermes plugin** (the v1 canonical platform). The satellite
core itself is platform-agnostic per Principle IV.

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

**Version**: 2.0.1 | **Ratified**: 2026-05-18 | **Last Amended**: 2026-05-20
