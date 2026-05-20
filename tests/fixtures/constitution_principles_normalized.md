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

