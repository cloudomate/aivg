# Specification Quality Checklist: Opus upstream (mic → STT) voice

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-06-04
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`.
- **Domain-quantity note**: the spec names "Opus", "raw 16 kHz PCM", "upstream/
  downstream", and "STT" as *problem-domain* facts (the existing wire reality),
  not implementation choices. The wire shape for advertising/​carrying upstream
  Opus (a new negotiated upstream codec + an Opus-carrying mic frame) is left to
  `/speckit-plan`.
- **No clarifications needed**: the user scoped it to "gateway and sdks"; the
  reasonable defaults (gRPC native tier + C++ SDK primary; WebRTC already Opus;
  esphome out of scope; raw-PCM fallback; additive contract; STT-transparent) are
  documented in Assumptions rather than raised as questions. The one judgement
  call — whether Opus upstream is opt-in or default — is left for planning/SDK
  design and does not change spec scope.
