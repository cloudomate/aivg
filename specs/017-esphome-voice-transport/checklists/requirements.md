# Specification Quality Checklist: ESPHome Voice Assistant transport

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-05-20
**Feature**: [spec.md](../spec.md)

## Content Quality

- [X] No implementation details (languages, frameworks, APIs)
- [X] Focused on user value and business needs
- [X] Written for non-technical stakeholders
- [X] All mandatory sections completed

## Requirement Completeness

- [X] No [NEEDS CLARIFICATION] markers remain
- [X] Requirements are testable and unambiguous
- [X] Success criteria are measurable
- [X] Success criteria are technology-agnostic (no implementation details)
- [X] All acceptance scenarios are defined
- [X] Edge cases are identified
- [X] Scope is clearly bounded
- [X] Dependencies and assumptions identified

## Feature Readiness

- [X] All functional requirements have clear acceptance criteria
- [X] User scenarios cover primary flows
- [X] Feature meets measurable outcomes defined in Success Criteria
- [X] No implementation details leak into specification

## Notes

- This spec deliberately names "ESPHome" and "protobuf" and the well-known port `6053` in the body — those are user-facing scope decisions (the feature's identity is "speak ESPHome's wire to existing ESPHome voice satellites"), not implementation leakage.
- The Apache-2 / Python-protobuf / `aioesphomeapi` references appear ONLY in the Dependencies + Open Questions blocks, where library-choice tradeoffs belong.
- **All three open questions resolved** in `/speckit-clarify` Session 2026-05-20 (see spec ## Clarifications):
  - Q1 → **`aioesphomeapi`** (depend on the upstream PyPI lib for proto types + framing helpers; mirrors OHF-Voice's `linux-voice-assistant`)
  - Q2 → **one `asyncio.Task` per connected device** (matches the aiortc-session pattern; FR-021 binds it)
  - Q3 → **reuse `aivg_core.webrtc.session.Session` verbatim** via the existing `MediaTransport` Protocol seam (FR-009 binds it)
- **Positioning was the unblocking decision** for this feature, not engineering. After reviewing the OHF-Voice / linux-voice-assistant precedent (which uses the ESPHome protocol verbatim instead of WebRTC for the satellite path) and weighing the "why not just use ESPHome Voice?" question against AIVG's agent-backend-flexibility positioning, the user chose to ship the ESPHome transport on the gateway FIRST (this feature) and the libaivg-sat C++ SDK SECOND (feature 016, narrowed to Linux/macOS/RPi Tier A only). This sequence inverts the original plan but unlocks the embedded story immediately by reusing the existing ESPHome firmware ecosystem.
- The constitutional Principle IV obligation (one `AgentPlatform`, transport-agnostic) is the central design promise of this feature — Q3 picks the smallest-blast-radius approach to honour it. The grep-gate SC-005 binds it.
- All five user stories are independently testable; US1 (HA Voice PE drop-in) is the MVP, US2 (no breakage of WebRTC clients) is the wire-compatibility regression boundary, US3 (one `AgentPlatform`, two transports) is the constitutional gate, US4 (multi-device concurrency) is the scale gate, US5 (management plane integration) is the operator-experience gate.

Ready for `/speckit-clarify`.
