# Implementation Plan: Speak Clean Prose — Reuse Hermes's TTS Markdown Stripper

**Branch**: `009-tts-text-normalization` | **Date**: 2026-05-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/009-tts-text-normalization/spec.md`

## Summary

The satellite speaks Markdown aloud because its bridge calls Hermes's
synthesis entrypoint `tools.tts_tool.text_to_speech_tool()` **without**
first calling Hermes's own sibling helper `tools.tts_tool.`
`_strip_markdown_for_tts()` — in Hermes, markdown-stripping is a *caller*
responsibility (the gateway `_send_voice_reply` and the CLI streaming
speaker both call it themselves). Fix: apply
`_strip_markdown_for_tts(text)` to the text immediately before
`text_to_speech_tool(text)` inside `HermesV013Bridge.tts_synthesize`.
Because **both** the feature-008 streaming path (`agent_stream` → per-unit
`tts_synthesize`) and the feature-006 fallback (`tts_stream` → per-unit
`tts_synthesize`) funnel through that one method, a single insertion point
covers both (FR-001/FR-002). No new normalizer, no emoji code, no config,
no agent-prompt change, no engine — pure reuse of the exact Hermes
function Hermes's own voice modes use (constitution I/IV; clarify-recorded).

## Technical Context

**Language/Version**: Python 3.11 (project + Hermes venv)
**Primary Dependencies**: none new — reuses the already-depended-on
host-only `tools.tts_tool` (lazy-imported in `hermes_bridge`); no package
added
**Storage**: N/A
**Testing**: `pytest` — existing suite (82) stays green with no edits; one
new local unit test asserts the strip→synth WIRING via an injected fake
`tools.tts_tool` (real strip semantics are Hermes-owned, host-proven)
**Target Platform**: local Hermes install (hermes-agent v0.14.0,
`~/.hermes/hermes-agent`), all-localhost; reused `deploy/deploy-local.sh`
**Project Type**: single project (existing `src/` + `tests/`)
**Performance Goals**: no perceptible added latency / TTFW — one cheap
per-sentence regex pass, identical to what Hermes already runs in its own
voice modes (SC-008)
**Constraints**: behaviour MUST equal `_strip_markdown_for_tts(reply)`
exactly (no added transform); agent output / display / transcript
byte-unchanged; existing automated suite unchanged with no test edits
**Scale/Scope**: ~1 import + ~3 lines at one site in
`hermes_bridge.py::tts_synthesize`; +1 small unit test; 0 other files

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Thin Satellite, Gateway-Owned Intelligence (NON-NEGOTIABLE)** —
  PASS. No engine instantiated; the only addition is calling an existing
  Hermes helper. STT/agent/TTS remain Hermes-reached unchanged. The text
  transform itself is Hermes's, not ours.
- **II. Generic Four-Plane Contract** — PASS. No plane semantics, shared
  models, or gateway behaviour change; speech is still the playback plane.
- **III. Separate Control and Voice Connections** — PASS. No connection,
  signaling, or datachannel change.
- **IV. Reuse Hermes, Don't Rebuild** — PASS (exemplary). The entire
  feature is a single call to Hermes's own `_strip_markdown_for_tts`,
  exactly where/how Hermes's `_send_voice_reply` calls it. No new config
  key, no new loader, no rebuilt behaviour. The clarify session explicitly
  rejected a bespoke normalizer / new `voice:` keys on these grounds.
- **V. Research-Backed, Constraint-Driven Decisions** — PASS. The host
  was researched during `/speckit-clarify` (recorded in spec
  `## Clarifications` + research.md): `_strip_markdown_for_tts` exists,
  `text_to_speech_tool` does not self-strip, Hermes callers strip
  themselves, no emoji handling exists, no real length cap. The
  deterministic wiring is locally unit-tested; real strip semantics +
  end-to-end speech are host-proven by the live spoken test (same
  discipline as 005/006/008).

**Result: PASS — no violations. Complexity Tracking not required.**

Post-Phase-1 re-check: still PASS (design adds no new surface beyond the
single reused call + a wiring test; see Phase 1 below).

## Project Structure

### Documentation (this feature)

```text
specs/009-tts-text-normalization/
├── plan.md              # This file
├── research.md          # Phase 0 (host findings consolidated from clarify)
├── data-model.md        # Phase 1 (text-flow entities; no persistence)
├── quickstart.md        # Phase 1 (verify + live spoken test + deploy)
├── contracts/
│   └── tts-strip-seam.md # Phase 1 (the bridge↔Hermes-helper contract)
├── checklists/
│   └── requirements.md  # /speckit-specify + /speckit-clarify output
└── tasks.md             # /speckit-tasks output (NOT created here)
```

### Source Code (repository root)

```text
src/hermes_satellite_adapter/
└── hermes_bridge.py     # ONLY changed file — HermesV013Bridge.tts_synthesize:
                          #   lazy-import _strip_markdown_for_tts alongside
                          #   text_to_speech_tool; strip the text before synth;
                          #   on import/strip failure fall back to raw text
                          #   (FR-008); empty-after-strip → skip via the
                          #   existing per-unit skip (FR-007)

tests/unit/
└── test_tts_strip.py    # NEW — injects a fake `tools.tts_tool`
                          #   (_strip_markdown_for_tts + text_to_speech_tool)
                          #   and asserts tts_synthesize feeds the STRIPPED
                          #   text to synth (FR-001/FR-002 wiring, parity,
                          #   order) + the FR-008 raw-fallback path

# unchanged: adapter.py, session.py, streamasm.py, signaling.py, media.py,
# textseg.py, management.py, the 008/006 paths (they call tts_synthesize,
# so they inherit the fix), deploy/* (reuse deploy-local.sh)
```

**Structure Decision**: Existing single-project layout. The change is
localized to one method (`HermesV013Bridge.tts_synthesize`) so it
automatically covers feature-008 streaming and feature-006 fallback (both
synthesize through it). One new isolated unit test; no other source,
contract, transport, or deploy file is touched.

## Complexity Tracking

> Not applicable — Constitution Check passed with no violations (this
> feature *removes* complexity by deferring entirely to a Hermes helper).
