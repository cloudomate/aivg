# Feature Specification: Make the Voice Turn Feel Snappy — Instrument & Reduce End-of-Speech → First-Word Latency

**Feature Branch**: `010-voice-turn-latency`
**Created**: 2026-05-19
**Status**: Draft
**Input**: User description: "i want to improve the latency today after user
is done speaking to first utterance by tts; feels sluggish — let's instrument
and work on improving the user experience"

## Overview

After feature 008 (streaming) and 009 (clean speech), the spoken answer is
correct but the gap between *the person finishing their sentence* and *the
first word coming back* feels sluggish. Live observation this session showed
a long, mostly invisible delay between "user stopped talking" and "first
audio" — but it is currently not measured, so it is not known which stage
(detecting the person stopped, recognizing the speech, the agent starting to
answer, producing the first spoken sentence, or playback) actually dominates.

This feature has two parts, in order:

1. **Instrument the turn**: produce a clear, per-stage timing breakdown for
   every voice turn — from "speaker finished" through "endpoint detected",
   "speech recognized", "agent's first output", "first sentence ready",
   "first synthesized audio", to "first audio played" — so the dominant
   cost is evidence, not guesswork.
2. **Reduce the dominant latency**: using that evidence, cut the
   end-of-speech → first-audible-word time, by tuning gateway-owned
   behaviour (recognition/endpointing settings the system already exposes)
   and by removing any avoidable waiting the satellite itself introduces
   (e.g. making sure the streaming pipeline truly overlaps and nothing
   blocks the first sentence) — **without** rebuilding speech recognition,
   endpointing, the agent, or speech synthesis (those remain gateway-owned;
   feature 008 streaming and 009 clean speech must not regress).

The deliverable is a measurably snappier turn plus the standing
instrumentation that proves it and guards against regressions.

## Clarifications

### Session 2026-05-19

- Q: Does 010 only instrument + expose knobs, or also change values to
  deliver the speed-up? → A: **Configurable params + faster, fully
  reversible defaults applied by the local deploy** (the ≥40% is delivered
  out-of-the-box and measured; the operator can override via config or
  restore the backup — same pattern `deploy-local.sh` already uses for the
  streaming block).
- Q: Is the per-stage instrumentation always-on or config-controlled? →
  A: **Always-on lightweight record (so regressions are always caught),
  with detail level / enable a configurable knob in the existing
  `satellite:` config block (default on); near-zero overhead.**
- Decided from the user directive ("any fine-tuning parameters MUST be
  configurable, not hardcoded") + constitution IV: **no tuning value is a
  hardcoded code constant.** Gateway/engine-and-endpoint knobs are the
  *existing* Hermes `~/.hermes/config.yaml` keys (e.g. recognition model,
  endpoint silence), inherited and read — never re-declared or overridden
  in adapter code. Any satellite-side knob lives in the *existing*
  `satellite:` block (loaded by the existing `SatelliteAdapterConfig`) with
  a safe default — **no new config file, loader, or secret store.**

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The reply starts noticeably sooner after I stop talking (Priority: P1)

A person asks a normal short question and stops speaking. Instead of an
uncomfortable multi-second silence, the first words of the answer come back
quickly enough that the exchange feels like a conversation.

**Why this priority**: This is the entire complaint — perceived
sluggishness from end-of-speech to first word. It is the user-facing goal.

**Independent Test**: Ask the same short prompt before and after the change
on the local install; the time from the speaker finishing to the first
audible word is reduced by a clear, recorded margin and feels responsive.

**Acceptance Scenarios**:

1. **Given** a short spoken question, **When** the person stops speaking,
   **Then** the first word of the answer is heard within a short, agreed
   target and noticeably sooner than the recorded pre-change baseline.
2. **Given** a long-answer question, **When** the person stops speaking,
   **Then** time-to-first-word is still within target (the streaming first
   sentence is not delayed by later content — feature 008 preserved).
3. **Given** the change is active, **When** any turn runs, **Then** the
   answer is still correct and clean (feature 009) and barge-in still works
   (no correctness or interruption regression).

---

### User Story 2 - The latency is measurable per stage (Priority: P1)

The operator can see, for any voice turn, how long each stage took
(end-of-speech → endpoint detected → speech recognized → agent first
output → first sentence ready → first audio synthesized → first audio
played), so improvement work targets the real bottleneck and regressions
are caught.

**Why this priority**: "Instrument" is half the explicit request, and
constitution V requires evidence before relying on a change. Without it,
any tuning is guesswork and un-provable.

**Independent Test**: Run a turn and read off a single, coherent per-stage
timing breakdown for that turn; the stage durations sum to the observed
end-to-end latency.

**Acceptance Scenarios**:

1. **Given** any completed voice turn, **When** its timing is inspected,
   **Then** each defined stage has a duration and the dominant stage is
   identifiable.
2. **Given** a before/after comparison, **When** the same prompt is run,
   **Then** the breakdown shows which stage improved and by how much.
3. **Given** a turn where a stage is unusually slow, **When** the breakdown
   is read, **Then** the slow stage is obvious without code inspection.

---

### User Story 3 - Faster without rebuilding engines; reversible (Priority: P2)

The speed-up comes only from gateway-owned settings and from removing
avoidable satellite-side waiting — no speech-recognition, endpointing,
agent, or synthesis engine is reimplemented — and it ships via the
existing local, backed-up, reversible deploy with no pre-existing platform
affected.

**Why this priority**: Established architectural and safety posture; a
faster turn that forks engine behaviour or is irreversible is not
acceptable.

**Independent Test**: Confirm the change set is limited to gateway-owned
configuration and satellite scheduling/instrumentation; restoring the
backup returns the prior latency and behaviour.

**Acceptance Scenarios**:

1. **Given** the change, **When** it is reviewed, **Then** no new
   ASR/VAD/agent/TTS engine exists in the satellite and endpointing is
   still the gateway's own algorithm (only its exposed settings changed).
2. **Given** the backup is restored, **Then** latency and behaviour return
   to the pre-change state and pre-existing platforms are unaffected.

### Edge Cases

- Very short utterance ("yes", "stop") → end-of-speech → first word stays
  within target; endpoint detection does not add a fixed long wait.
- Long utterance (many seconds of speech) → recognition cost is visible in
  the breakdown and does not silently dominate without being attributable.
- Noisy input / false endpoint → instrumentation still records the turn;
  correctness is unaffected (no new endpointing logic introduced).
- A stage fails or the turn errors → the breakdown still reports the
  stages that did complete (instrumentation never hides a failure or
  hangs the turn).
- Long-answer turn → first-word target is met even though total speaking
  time is long (streaming overlap from feature 008 preserved).
- Barge-in mid-turn → instrumentation closes the turn cleanly; no skewed or
  never-ending measurement.
- Empty / tool-only answer → the turn still produces a coherent timing
  record (no missing or infinite stage).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST record, for every voice turn, timestamps that
  yield per-stage durations covering at least: end-of-user-speech →
  endpoint detected → speech recognition complete → agent first output →
  first speakable sentence ready → first audio synthesized → first audio
  delivered to the caller.
- **FR-002**: The per-turn breakdown MUST be observable by the operator
  after the fact (e.g. in the existing gateway log/diagnostics) as a single
  coherent record whose stage durations account for the end-to-end
  end-of-speech → first-word latency.
- **FR-003**: A pre-change baseline for a defined "typical short prompt"
  MUST be recorded using this instrumentation before any tuning, so
  improvement is measured against evidence (constitution V).
- **FR-004**: The system MUST reduce the end-of-speech → first-audible-word
  time for the typical short prompt by a clear, agreed margin versus the
  recorded baseline, with the breakdown showing which stage(s) improved.
  The local deploy MUST apply faster, fully reversible default values
  (backup-first) so the reduction is delivered out-of-the-box and measured
  — the operator can override via configuration or restore the backup to
  return to the prior values/latency.
- **FR-005**: Latency reduction MUST come only from (a) adjusting
  gateway-owned settings the system already exposes (e.g. recognition
  model / endpoint silence behaviour) and/or (b) removing avoidable
  waiting the satellite itself introduces; NO speech-recognition,
  endpointing, agent, or synthesis engine may be reimplemented in the
  satellite, and endpointing remains the gateway's own algorithm (only its
  exposed settings change).
- **FR-011**: Every fine-tuning parameter MUST be configuration-driven,
  NOT a hardcoded code constant. Gateway/engine-and-endpoint knobs MUST be
  the existing Hermes `~/.hermes/config.yaml` keys, inherited and read
  (never re-declared or overridden in adapter code); any satellite-side
  knob MUST live in the existing `satellite:` config block (existing
  loader) with a safe default. NO new config file, loader, or secret store
  (constitution IV).
- **FR-012**: The per-turn latency record MUST be produced for every turn
  by default (so regressions are always caught), with its detail level /
  enablement a configurable knob in the `satellite:` block (default on);
  the format/verbosity MUST NOT be a hardcoded-only behaviour.
- **FR-006**: Feature 008 (first sentence spoken while the agent is still
  composing) and feature 009 (clean spoken prose) MUST NOT regress;
  barge-in and multi-turn continuity MUST still work.
- **FR-007**: Instrumentation MUST add no perceptible latency of its own
  and MUST NOT alter what is spoken, displayed, or recorded.
- **FR-008**: Instrumentation MUST still produce a usable record when a
  turn errors, is interrupted (barge-in), or yields an empty/tool-only
  answer — never hang or emit an incoherent/never-closing measurement.
- **FR-009**: The change MUST be limited to instrumentation + gateway-owned
  configuration + satellite scheduling; media transport, signaling,
  control-plane, and turn/state-machine semantics MUST remain behaviourally
  compatible and the existing automated conversation suite MUST stay green
  with no test edits.
- **FR-010**: Redeployment MUST use the existing local, backup-first,
  reversible deploy path and MUST NOT degrade any pre-existing gateway
  platform; the production deploy script remains unchanged; restoring the
  backup returns the prior latency/behaviour.

### Key Entities *(include if feature involves data)*

- **Voice Turn**: one exchange; the unit a latency record is attached to
  (reused from features 001/005/006/008).
- **Latency Breakdown**: the ordered set of per-stage durations for a turn
  (end-of-speech → endpoint → recognition → agent-first-output → first
  sentence → first synth → first playback) plus the end-to-end total.
- **Turn Stage**: a named, timed segment of the turn with a start and end
  instant; stages are contiguous and sum to the end-to-end latency.
- **Baseline Record**: the pre-change Latency Breakdown for the agreed
  typical short prompt, the reference for the improvement target.
- **Gateway-Owned Setting**: an existing exposed Hermes config value
  (recognition model, endpoint silence behaviour) whose adjustment changes
  latency without reimplementing an engine — inherited/read, never
  hardcoded or re-declared in adapter code.
- **Tuning Parameter**: any value that affects the speed/quality
  trade-off; by FR-011 each is configuration-driven (Hermes config key, or
  the existing `satellite:` block with a safe default) — never a hardcoded
  constant.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For the agreed typical short prompt, the median
  end-of-speech → first-audible-word time is reduced by **at least 40%**
  versus the recorded pre-change baseline (same prompt, same local
  install).
- **SC-002**: For the typical short prompt, the first audible word is heard
  within **2 seconds** of the person finishing speaking on the local
  install (target; baseline expected to be well above this).
- **SC-003**: 100% of voice turns produce a per-stage Latency Breakdown
  whose stage durations sum (within a small tolerance) to the observed
  end-to-end latency, and from which the dominant stage is unambiguous.
- **SC-004**: A documented before/after comparison for the same prompt
  shows the specific stage(s) that improved and the magnitude (evidence
  for constitution V).
- **SC-009**: Zero tuning values are hardcoded code constants — every one
  is overridable via Hermes config or the `satellite:` block (verified by
  review + a test); changing a config value (or restoring the backup)
  changes (or reverts) the latency with no code change.
- **SC-005**: No regression: feature 008 long-answer time-to-first-word,
  feature 009 clean speech, barge-in stop responsiveness, and multi-turn
  continuity are all still met after the change.
- **SC-006**: The existing automated conversation suite remains 100% green
  with no test edits; any new deterministic measurement logic has its own
  passing tests.
- **SC-007**: Instrumentation overhead is not perceptible and does not
  change spoken/displayed/recorded content (the with/without-instrument
  spoken output is identical).
- **SC-008**: 0 regressions to pre-existing gateway platforms after the
  local redeploy; restoring the backup returns latency and behaviour to
  the prior state in under 5 minutes.

## Assumptions

- "Latency" means the user-perceived gap from the person finishing
  speaking to the first audible word of the answer; that is the metric to
  instrument and reduce.
- "Typical short prompt" is a fixed, agreed phrase used consistently for
  baseline and after measurements (e.g. a one-sentence question expecting a
  short answer); exact phrase chosen at plan/implement time and recorded.
- Likely dominant costs (to be confirmed by the instrumentation, not
  assumed): the endpoint silence wait and the speech-recognition step on
  the local install; the agreed levers are gateway-owned settings for
  those plus removing any avoidable satellite-side buffering — consistent
  with constitution I (no engine rebuilt) and IV (reuse gateway config).
- Instrumentation lives in the existing gateway log/diagnostics already
  used this project; no new external telemetry system is introduced. It is
  always-on (lightweight) with detail level / enable a configurable knob
  in the existing `satellite:` block, default on (clarify Q2).
- All tuning parameters are configuration-driven, never hardcoded
  (FR-011): engine/endpoint knobs are the existing Hermes config keys
  (inherited/read), satellite-side knobs the existing `satellite:` block;
  no new loader/store. The local deploy applies faster, fully reversible
  default values (backup-first, like the existing streaming-block step) so
  the improvement ships out-of-the-box yet the operator can override or
  restore (clarify Q1).
- Reuses features 001/005/006/008/009 unchanged except for adding timing
  capture and applying settings/scheduling; the Hermes-owned engines and
  the reversible local deploy are reused as-is.
- A target of ≥40% reduction and a ≤2 s first-word goal are working targets
  refined once the baseline is measured; the binding requirement is a
  clear, evidence-backed improvement with no regression.
- Real responsiveness is confirmed by a human listening test on the local
  install (consistent with prior features); deterministic measurement
  logic is unit-tested and the automated suite stays green.
- STT/agent/TTS engine internals, accuracy, and model training are out of
  scope; only timing, exposed settings, and satellite scheduling change.
