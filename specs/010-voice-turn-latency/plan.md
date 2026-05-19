# Implementation Plan: Make the Voice Turn Feel Snappy — Instrument & Reduce End-of-Speech → First-Word Latency

**Branch**: `010-voice-turn-latency` | **Date**: 2026-05-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/010-voice-turn-latency/spec.md`

## Summary

Two parts, in order: (1) **instrument** every voice turn with a per-stage
latency breakdown (end-of-speech → endpoint detected → STT done → agent
first output → first speakable sentence → first audio synthesized → first
audio delivered) emitted through the existing `LogSink`; (2) **reduce** the
dominant stage(s) using only Hermes-owned config values (recognition model,
endpoint silence) inherited & read — never hardcoded — plus removing any
avoidable satellite-side waiting, with the local deploy applying faster,
fully reversible defaults so the ≥40% ships out-of-the-box. No ASR/VAD/
agent/TTS engine reimplemented; endpointing stays Hermes's algorithm;
features 008 (streaming) / 009 (clean speech) / barge-in / multi-turn must
not regress. Every tuning value is configuration-driven (Hermes config keys
or the existing `satellite:` block via the existing `SatelliteAdapterConfig`
— no new loader/store, constitution IV).

## Technical Context

**Language/Version**: Python 3.11 (project + Hermes venv)
**Primary Dependencies**: none new — stdlib `time.monotonic`; reuse the
existing `LogSink` (diagnostics), `SatelliteAdapterConfig` (the `satellite:`
block), and Hermes `~/.hermes/config.yaml` keys (`stt.local.model`,
`voice.silence_duration`/`silence_threshold`)
**Storage**: N/A (per-turn record is logged, not persisted)
**Testing**: `pytest` — existing suite (88) stays green with NO edits; new
unit tests for the deterministic latency-record assembly (stages → ordered
breakdown that sums to total; robust to missing/interrupted/error stages)
**Target Platform**: local Hermes install (hermes-agent v0.14.0,
`~/.hermes/hermes-agent`), all-localhost; reused `deploy/deploy-local.sh`
**Project Type**: single project (existing `src/` + `tests/`)
**Performance Goals**: end-of-speech → first-audible-word for the agreed
typical short prompt reduced ≥40% vs recorded baseline, ≤2 s target
(SC-001/SC-002); instrumentation overhead not perceptible (SC-007)
**Constraints**: no engine reimplemented; endpointing stays Hermes's
(constitution I); every tuning value config-driven, zero hardcoded
constants (FR-011/SC-009); 008/009/barge-in/multi-turn no regression
(FR-006); existing automated suite green, no test edits (FR-009/SC-006);
reversible local deploy, production script untouched (FR-010)
**Scale/Scope**: timestamp capture at ~6 existing seams in `session.py` +
`hermes_bridge.agent_stream`; 1 small pure module for the breakdown; read
1 instrumentation knob from the `satellite:` block; `deploy-local.sh` adds
an idempotent/backup-first/reversible faster-defaults step (same pattern as
its existing streaming-block step); ~no other surface

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Thin Satellite, Gateway-Owned Intelligence (NON-NEGOTIABLE)** —
  PASS. Only existing seam timestamps + emitting a log record + changing
  Hermes *config values*. No STT/VAD/agent/TTS engine added; endpointing
  remains Hermes's server-side silence algorithm (only its exposed
  `voice.*` settings are tuned); STT model swap is a Hermes config value,
  not a re-implementation.
- **II. Generic Four-Plane Contract** — PASS. No plane semantics, shared
  models, or gateway behaviour change; a turn still means the same thing.
- **III. Separate Control and Voice Connections** — PASS. No connection,
  signaling, or datachannel change; the breakdown rides the existing
  control-plane diagnostics (`LogSink`), not a new channel.
- **IV. Reuse Hermes, Don't Rebuild** — PASS (exemplary). Reuses Hermes
  config keys (inherited/read), the existing `LogSink`, the existing
  `SatelliteAdapterConfig`/`satellite:` block, and `deploy-local.sh`. No
  new config file, loader, or secret store; no hardcoded tuning constants
  (FR-011). The deploy applies faster *config* defaults the same
  backup-first/idempotent way it already sets the streaming block.
- **V. Research-Backed, Constraint-Driven Decisions** — PASS (this feature
  *is* Principle V): measure first (instrument + record a baseline), then
  change only the evidenced dominant stage, then prove the before/after on
  the host. The deterministic record-assembly is unit-tested; the real
  wall-clock win + STT-model swap are host-proven by the live spoken test.

**Result: PASS — no violations. Complexity Tracking not required.**

Post-Phase-1 re-check: still PASS (design adds only timestamp capture, one
pure record module, a config read, and a reversible deploy config step —
no new engine/loader/channel; see Phase 1).

## Project Structure

### Documentation (this feature)

```text
specs/010-voice-turn-latency/
├── plan.md              # This file
├── research.md          # Phase 0 (stage map, config levers, testable slice)
├── data-model.md        # Phase 1 (LatencyBreakdown / TurnStage / Baseline)
├── quickstart.md        # Phase 1 (baseline → tune → before/after → deploy)
├── contracts/
│   └── latency-record.md # Phase 1 (L1–Ln record + config + no-regress)
├── checklists/
│   └── requirements.md  # /speckit-specify + /speckit-clarify output
└── tasks.md             # /speckit-tasks output (NOT created here)
```

### Source Code (repository root)

```text
src/hermes_satellite_adapter/
├── turnlatency.py       # NEW — pure: collect stage instants → ordered
│                        #   LatencyBreakdown that sums to total; tolerant
│                        #   of missing/interrupted/error stages
│                        #   (deterministic, unit-testable slice — const. V)
├── session.py           # CHANGED — capture stage instants at the existing
│                        #   seams (endpoint-detected, stt start/done,
│                        #   first-audio-delivered); emit ONE consolidated
│                        #   breakdown via the existing self._log/LogSink at
│                        #   "turn complete"; robust on error/barge-in/empty
├── hermes_bridge.py     # CHANGED (small) — agent_stream records agent
│                        #   first-delta / first-unit-ready / first-synth
│                        #   instants into the turn (host-only seam)
└── config.py            # CHANGED (small) — read instrumentation verbosity/
                          #   enable from the EXISTING satellite: block
                          #   (default on); no new loader (FR-012/FR-011)

deploy/
└── deploy-local.sh      # CHANGED — add an idempotent, backup-first,
                          #   REVERSIBLE step setting faster Hermes defaults
                          #   (stt.local.model, voice.silence_duration) the
                          #   same way it already sets the streaming block
                          #   (FR-004/FR-010); production deploy-to-hermes.sh
                          #   UNCHANGED

tests/unit/
└── test_turnlatency.py  # NEW — the breakdown assembly: ordered, sums to
                          #   total within tolerance, dominant-stage
                          #   identifiable, missing/interrupted/error stages
                          #   handled (SC-003/FR-008); + a no-hardcode/
                          #   config-read assertion (SC-009/FR-011)

# unchanged: streamasm.py, adapter.py, signaling.py, media.py, textseg.py,
# management.py, contracts of 001/005/006/008/009, production deploy script
```

**Structure Decision**: Existing single-project layout. The deterministic,
locally-provable slice is isolated in a new pure `turnlatency.py` (mirrors
`streamasm.py`/`textseg.py`). `session.py` owns most stage instants (it
already drives the turn loop and the `LogSink`); `hermes_bridge.agent_stream`
contributes the three agent/synth instants it alone sees. Reduction is
delivered by Hermes *config values* applied through the existing reversible
`deploy-local.sh` — no engine, loader, channel, or hardcoded constant.

## Complexity Tracking

> Not applicable — Constitution Check passed with no violations. The
> feature adds measurement + config-driven tuning only; it introduces no
> architectural complexity (one pure module, existing seams/loader/deploy).
