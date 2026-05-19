# Contract: Voice-Turn Latency Record, Config & No-Regression

Behavioural contract for feature 010. Stage names per data-model.md.

## L1 — Per-turn breakdown emitted (FR-001/FR-002)

Every voice turn MUST, on completion, emit exactly one consolidated
latency record via the existing `LogSink` (`session._log`, the
`"turn complete"` line or adjacent) containing the per-stage durations for
the canonical sequence plus the end-to-end total. One coherent record per
turn — not scattered lines.

## L2 — Stages sum to total (SC-003)

Present stage durations MUST sum to the observed end_of_speech →
first_audio_delivered span within a small tolerance, and the dominant
stage MUST be unambiguously identifiable from the record. Assembly is the
pure `turnlatency.py` (deterministic; stdlib only).

## L3 — Robust on error / barge-in / empty (FR-008)

If the turn errors, is interrupted (barge-in), or yields an empty/
tool-only answer, the record MUST still be emitted with the stages that
completed (later stages omitted, not faked, not infinite). Instrumentation
MUST never hang the turn or emit a never-closing measurement.

## L4 — Emit-only, content-neutral (FR-007/SC-007)

Instrumentation MUST NOT change what is spoken, displayed, or recorded,
MUST add no perceptible latency, and the with/without-instrument spoken
output MUST be identical.

## L5 — Baseline before tuning (FR-003/SC-004)

A Baseline Record for the agreed typical short prompt MUST be captured via
this instrumentation BEFORE any config tuning, and a documented
before/after for the same prompt MUST show which stage(s) improved and by
how much (Principle V evidence).

## L6 — Improvement delivered & reversible (FR-004/SC-001/SC-002/SC-008)

End-of-speech → first-audible-word for the typical short prompt MUST be
reduced ≥40% vs the Baseline (target ≤2 s), delivered by the local deploy
applying faster defaults. Restoring the timestamped config backup MUST
return the prior latency in < 5 min; pre-existing platforms unaffected.

## L7 — Config-driven, nothing hardcoded (FR-011/FR-012/SC-009)

Every tuning value MUST be read from configuration: engine/endpoint knobs
from the existing Hermes `~/.hermes/config.yaml` keys (inherited/read,
never re-declared/overridden in code); any satellite-side knob (incl.
instrumentation verbosity/enable) from the EXISTING `satellite:` block via
the EXISTING `SatelliteAdapterConfig`. No new config file/loader/secret
store. Zero tuning values as hardcoded constants — verifiable by review +
a test; changing a config value (or restoring the backup) changes (or
reverts) latency with no code change.

## L8 — No engine rebuilt; no regression (FR-005/FR-006/FR-009/SC-005/SC-006)

No ASR/VAD/agent/TTS engine reimplemented; endpointing remains Hermes's
algorithm (only its exposed `voice.*` settings change); STT model is a
Hermes config value. Features 008 (first sentence while generating), 009
(clean speech), barge-in stop responsiveness, and multi-turn continuity
MUST still pass. Media transport / signaling / control-plane / turn-state
semantics behaviourally unchanged; the existing automated suite stays 100%
green with NO test edits; production deploy script untouched.

## Verification

- **Local (L2/L3/L7 deterministic)**: `tests/unit/test_turnlatency.py` —
  ordered breakdown sums to total within tolerance, dominant stage exposed,
  missing/interrupted/error stages handled; a test asserts tuning values
  are read from config (no hardcoded constant). Full `pytest -q` stays
  green with NO existing-test edits (L8/SC-006).
- **Host (L1/L4/L5/L6/L8 end-to-end)**: live spoken test on the local
  gateway — record the Baseline for the agreed prompt, apply the
  reversible faster defaults, re-measure: ≥40% reduction with the
  before/after breakdown showing the improved stage(s); 008/009/barge-in/
  multi-turn still good; backup-restore reverts in < 5 min (quickstart).
