# Feature Specification: Stream the Spoken Answer via the Agent Text-Delta Seam

**Feature Branch**: `008-agent-delta-streaming`
**Created**: 2026-05-19
**Status**: Draft
**Input**: User description: "Stream the agent reply via the Hermes agent
text-delta callback (the cli.py voice-mode pattern), not the draft/platform
hook. Re-architect the satellite's agent turn … run the Hermes agent the way
Hermes's own CLI voice mode does … feed deltas into the feature-006 unit
assembler → per-sentence Hermes TTS → WebRTC playback … STT/agent/TTS remain
Hermes-owned … mandatory fallback to feature 006 … supersedes feature 007's
draft-hook approach, confirmed not reachable for the LOCAL/voice path on
hermes-agent v0.14.0. Deploy/test target is the LOCAL Hermes install."

## Overview

The caller should hear the answer begin while the agent is still composing the
rest of it — conversational time-to-first-word for long answers. Feature 006
delivered sentence-by-sentence *playback*, but only after the whole reply was
composed. Feature 007 tried to obtain the reply incrementally through Hermes's
platform **draft-streaming hook**; live debugging on the local Hermes install
(hermes-agent v0.14.0) **proved that hook is never driven for the satellite's
programmatic/voice path** (its stream consumer is never even instantiated for
that path). The same incremental capability, however, *does* exist and is used
by Hermes's own CLI and Discord voice modes through a different, sanctioned
seam: the **agent text-delta stream** (the agent emits text deltas as it
generates; a sentence buffer turns them into spoken sentences in real time).

This feature re-sources the reply through that proven seam: obtain the agent's
output incrementally as it is produced, feed it into feature 006's existing
sentence assembly → per-sentence speech → playback, so the first sentence is
spoken within a couple of seconds while later sentences are still being
written. It supersedes feature 007's approach. The agent, speech recognition,
and speech synthesis remain owned by Hermes exactly as they are for Hermes's
own voice modes; the satellite only supplies the incremental sink, the audio
transport, and barge-in — its established role. If the incremental stream is
unavailable for a turn, behaviour degrades to feature 006 with no regression.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The answer begins before the agent has finished thinking (Priority: P1)

A person asks something with a long, multi-part answer. Instead of a long
silence while the whole answer is composed, they hear the first sentence
within a couple of seconds and the answer continues smoothly as the agent
keeps producing it.

**Why this priority**: This is the entire point — conversational
time-to-first-word for long answers, which neither feature 006 nor the
(non-functioning) feature 007 path delivers on this build.

**Independent Test**: Ask a question whose full answer takes the agent a long
time to compose; the first audible sentence is heard far sooner than the agent
could have finished the whole answer, on the local Hermes install.

**Acceptance Scenarios**:

1. **Given** the agent is generating a multi-sentence answer, **When** the
   first complete sentence is available from the incremental stream, **Then**
   it is spoken without waiting for the remaining sentences to be generated.
2. **Given** a long answer, **When** the agent is still composing later
   sentences, **Then** earlier sentences are already being spoken and speech
   continues without large gaps as new sentences arrive.
3. **Given** a short single-sentence answer, **When** it is produced, **Then**
   behaviour is at least as fast as feature 006 (no regression).

---

### User Story 2 - Barge-in interrupts a still-generating answer (Priority: P1)

While the answer is being spoken **and the agent is still generating more of
it**, the person talks over it. Speech stops promptly, the agent stops
producing the rest, nothing further is spoken, and the new utterance becomes
the next turn.

**Why this priority**: Interrupting is most valuable mid-long-answer;
streaming generation must not make barge-in slower or leave the agent running
in the background.

**Independent Test**: During a still-generating spoken answer, speak; speech
stops promptly, no later sentence is spoken, and the interrupted answer's
remaining generation is abandoned.

**Acceptance Scenarios**:

1. **Given** an answer is mid-generation and mid-playback, **When** the person
   speaks, **Then** playback stops promptly, no not-yet-spoken or
   not-yet-generated sentence is spoken, and continued generation of that
   answer is abandoned.
2. **Given** an interruption, **When** the agent responds again, **Then** the
   new answer addresses the interrupting utterance and itself streams.

---

### User Story 3 - Reversibly deploy on the local Hermes install (Priority: P2)

The operator deploys the re-architected adapter to the **local** Hermes
install via the existing local, backed-up, reversible deploy path;
pre-existing gateway platforms remain unaffected.

**Why this priority**: Established safety posture; the improvement has no value
until it is the running version and remains reversible.

**Independent Test**: Local redeploy → streaming-from-generation live, both
planes listening, pre-existing platforms intact; restoring the prior backup
returns to the previous state.

**Acceptance Scenarios**:

1. **Given** the new adapter, **When** the local deploy runs, **Then** the
   host-mutating step is confirmed and the config is backed up first.
2. **Given** the backup is restored, **Then** the gateway returns to its
   pre-deploy state.

### Edge Cases

- The incremental stream is unavailable / not produced for a turn → the system
  MUST degrade to feature 006 behaviour (segment the completed reply) with no
  error and no worse latency than 006.
- The agent emits its whole answer effectively in one delta → behaves at least
  as well as feature 006 (single segmentation pass).
- Deltas arrive that do not yet form a complete sentence → partial text is
  buffered until a speakable unit is available; no half-sentence is spoken.
- The agent revises/retracts already-emitted text → already-spoken audio
  cannot be unsaid; behaviour remains coherent (only finalized text spoken).
- The agent stalls mid-generation → earlier sentences keep playing; the
  session does not wedge or falsely end the turn.
- Agent generation finishes faster than speech → remaining sentences queue and
  still play in order (feature 006 behaviour).
- Barge-in while the agent is still generating → generation is abandoned
  promptly; no orphaned background agent work continues.
- Empty / tool-only answer → nothing is spoken; session returns to listening.
- Agent or speech provider fails mid-stream → the turn fails perceptibly
  rather than hanging; no broken/zero-length audio.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST obtain the agent's answer **incrementally as it
  is generated** via the same sanctioned agent text-delta mechanism Hermes's
  own CLI/Discord voice modes use — not the platform draft-streaming hook.
- **FR-002**: The system MUST begin speaking as soon as the first complete
  speakable unit is available from the incremental stream, without waiting for
  the agent to finish composing the whole answer.
- **FR-003**: Later sentences MUST continue to be spoken in order as the agent
  produces them, with natural pacing and no audible overlap; incremental text
  MUST be assembled into complete speakable units before synthesis (no
  half-sentence audio).
- **FR-004**: Barge-in MUST stop playback promptly, abandon all not-yet-spoken
  and not-yet-generated content, AND stop the agent continuing to generate the
  interrupted answer (no orphaned background generation).
- **FR-005**: If the incremental stream is unavailable for a turn, the system
  MUST gracefully fall back to feature 006 behaviour (speak the completed
  reply sentence-by-sentence) with no error and no worse than 006.
- **FR-006**: Speech recognition, the agent loop, and speech synthesis MUST
  remain Hermes-owned and reached the same way Hermes's own voice modes reach
  them (Hermes's agent run with a delta sink + Hermes STT/TTS) — no
  ASR/agent/TTS engine reimplemented in the adapter (constitution I/IV).
- **FR-007**: Short / empty / tool-only answers MUST behave at least as well
  as feature 006 (no latency or correctness regression).
- **FR-008**: An agent or speech failure mid-stream MUST surface as a
  perceptible turn failure, not a hang or silent stall.
- **FR-009**: The change MUST be limited to how the reply is obtained and
  timed; the media transport contract, signaling, control plane, and
  turn/state-machine semantics MUST remain behaviourally compatible (feature
  001 fake-transport suite stays green with no test edits).
- **FR-010**: Redeployment MUST use the existing **local**, backup-first,
  reversible deploy path (`deploy/deploy-local.sh`) and MUST NOT degrade any
  pre-existing gateway platform; the production ssh deploy script remains
  unchanged.
- **FR-011**: This feature supersedes feature 007's draft-streaming-hook
  approach for delivering incremental speech; feature 007's locally-provable
  assembler and its unit tests are reused unchanged.
- **FR-012**: Multi-turn conversation continuity MUST be preserved at parity
  with feature 006: switching from the gateway-managed `handle_message` path
  to running the agent directly MUST NOT drop session/conversation context —
  a follow-up turn MUST still see the prior turns' context (the agent run is
  given the same session identity and prior conversation history Hermes would
  have supplied via the previous path). No multi-turn memory regression.

### Key Entities *(include if feature involves data)*

- **Incremental Answer**: the agent's reply as a sequence of text deltas
  produced over time rather than one final string.
- **Speakable Unit**: reused from feature 006 — a sentence-sized chunk;
  assembled from incremental deltas as soon as a full unit is available.
- **Streaming Pipeline**: deltas → unit assembly → per-unit Hermes synthesis →
  in-order playback, all overlapped while the agent still generates.
- **Voice Session / Turn**: reused from features 001/005/006; a turn now both
  generates and speaks concurrently.
- **Hermes Agent / STT / TTS**: reused and Hermes-owned; the agent is run with
  an incremental text-delta sink and an abort signal for barge-in.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For an answer whose full composition takes the agent ≥10 s, the
  first audible sentence is heard within 3 seconds of the turn starting to be
  answered.
- **SC-002**: For a long answer, total time-to-first-word is reduced by at
  least 60% compared with feature 006 on the same prompt (006 baseline
  recorded for the same prompt before comparison).
- **SC-003**: Sentences play in order with no perceptible mid-answer silence
  gap longer than ~1.5 s while the agent is producing steadily, and no
  overlap/garble.
- **SC-004**: Barge-in during a still-generating answer stops audio within
  300 ms, zero not-yet-spoken sentences are spoken, and continued agent
  generation of that answer ceases within 1 s.
- **SC-005**: Short / empty / tool-only answers show no latency or correctness
  regression vs feature 006; when the incremental stream is unavailable the
  system is no worse than feature 006.
- **SC-006**: A long multi-sentence answer is fully intelligible and coherent
  end to end (no missing or duplicated sentences vs the agent's actual answer).
- **SC-007**: Feature 001's fake-transport conversation suite remains 100%
  green after this change, with no test edits.
- **SC-008**: 0 regressions to pre-existing gateway platforms after the local
  redeploy; restoring the backup returns the gateway to its prior state in
  under 5 minutes.

## Assumptions

- The user-visible goal is "hear the answer begin while the agent is still
  composing it." Phase-0 planning confirmed (live host debugging, recorded in
  feature 007 research) that Hermes exposes the agent text-delta stream the way
  its own CLI/Discord voice modes consume it; the exact in-codebase entrypoint
  (e.g. running the Hermes agent with a delta/stream callback as `cli.py`
  does) is verified against the running local install at plan/implement time
  (constitution V), with the FR-005 fallback as the safety net.
- Sentence assembly reuses feature 006/007's deterministic
  `IncrementalUnitAssembler` + segmentation unchanged; STT, the agent, and TTS
  remain Hermes-owned via the same calls Hermes's own voice modes use
  (constitution I/IV).
- Feature 006's per-sentence pipelined synthesis + incremental playback and
  feature 005's media transport are reused unchanged; only the reply *source*
  becomes the agent text-delta stream and barge-in also aborts agent
  generation.
- The deploy/test target is the **local** Hermes install (hermes-agent
  v0.14.0, `~/.hermes/hermes-agent`) via `deploy/deploy-local.sh`; no remote
  ssh host, no LAN, no tunnel — all-localhost, so WebRTC media works.
- Real end-to-end streaming behaviour is proven by the local live spoken test
  (a human at a microphone), consistent with constitution V; the
  fake-transport suite guards the unchanged conversation logic.
- TTS text normalization (emoji/markdown) and STT model choice remain out of
  scope (separate concerns); this feature changes only reply sourcing/timing.
