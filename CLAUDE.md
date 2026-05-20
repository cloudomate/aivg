<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan:
`specs/011-satellite-management/plan.md`
(prior features: 001-realtime-voice-adapter, 002-hermes-agent-skills, 003-deploy-test-adapter, 004-webrtc-signaling-site, 005-aiortc-media-transport, 006-streaming-tts, 007-live-agent-streaming [superseded by 008], 008-agent-delta-streaming [implemented + locally deployed], 009-tts-text-normalization [implemented + locally deployed; live host-proof pending], 010-voice-turn-latency [implemented + live-proven] under `specs/`)
Constitution: v2.0.0 — Principle IV widened from "Reuse Hermes" to "Reuse the upstream agent platform". Satellite system is agent-platform-agnostic via the `AgentPlatform` plugin seam; Hermes is the v1 canonical plugin (OpenClaw planned).
<!-- SPECKIT END -->
