<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan:
`specs/014-aivg-sat-sdk-ts/plan.md`
(prior features: 001-realtime-voice-adapter, 002-hermes-agent-skills, 003-deploy-test-adapter, 004-webrtc-signaling-site, 005-aiortc-media-transport, 006-streaming-tts, 007-live-agent-streaming [superseded by 008], 008-agent-delta-streaming [implemented + locally deployed], 009-tts-text-normalization [implemented + locally deployed; live host-proof pending], 010-voice-turn-latency [implemented + live-proven], 011-satellite-management [82/88 tasks complete; T019/T023/T045 partials], 012-aivg-branding [55/55 + Phase 9 shim removal landed], 013-aivg-setup-cli [MVP shipped + live-proven via pip-install + entry-point pivot] under `specs/`)
Project: **AIVG (AI Voice Gateway)** — formerly "Hermes Voice" through feature 011; renamed in feature 012. Hermes is the v1 agent-platform plugin; OpenClaw is a planned plugin.
Constitution: v2.0.1. Principle IV: satellite system is agent-platform-agnostic via the `AgentPlatform` plugin seam — feature 013 extended the seam to the deploy layer with `SetupCapability`; feature 014 ships `@aivg/sat-sdk` (TypeScript) as the first satellite-side client SDK, with feature 015 (C++ SDK) to follow.
<!-- SPECKIT END -->
