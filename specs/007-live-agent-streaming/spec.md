# Feature Specification: End-to-End Streaming Conversation (speak while the agent is still thinking)

**Feature Branch**: `007-live-agent-streaming`
**Created**: 2026-05-19
**Status**: Draft
**Input**: User description: "end-to-end streaming conversation: stream the
Hermes agent's response incrementally as it is generated and begin speaking it
sentence-by-sentence while the agent is still composing the rest, instead of
waiting for the full agent reply before any audio plays. Builds on feature
006 (which only streams TTS over the already-completed reply)."

## Overview

Feature 006 made the *spoken playback* stream sentence-by-sentence, but the
caller still waits in silence for the **entire** agent answer to be composed
before the first word is heard. Live testing confirmed this: a long reply
showed ~70 s where almost all the time was the agent generating the full text
up front; only then did sentence-by-sentence speech begin.

This feature closes that last gap: as the agent **produces** its answer, the
gateway speaks each sentence as soon as it is available — so for a long answer
the caller hears the first sentence within a couple of seconds and the rest
continues while the agent is still composing later sentences. The result is a
genuinely conversational latency, like talking to a person who starts
answering before they've finished their whole thought.

It changes only how the reply is *obtained and timed* (incremental instead of
one final block) and reuses feature 006's segmentation/pipelined playback and
feature 005's media transport. Barge-in, the control/voice split, and the
thin-satellite boundary are preserved.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The answer begins before the agent has finished thinking (Priority: P1)

A person asks something with a long, multi-part answer. Instead of a long
silence while the whole answer is composed, they hear the first sentence
within a couple of seconds and the answer continues smoothly as the agent
keeps producing it.

**Why this priority**: This is the entire point — conversational
time-to-first-word for long answers, which feature 006 alone does not deliver.

**Independent Test**: Ask a question whose full answer takes the agent a long
time to compose; the first audible sentence is heard far sooner than the
agent could have finished the whole answer.

**Acceptance Scenarios**:

1. **Given** the agent is generating a multi-sentence answer, **When** the
   first sentence is available, **Then** it is spoken without waiting for the
   remaining sentences to be generated.
2. **Given** a long answer, **When** the agent is still composing later
   sentences, **Then** earlier sentences are already being spoken and the
   speech continues without large gaps as new sentences arrive.
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

1. **Given** an answer is mid-generation and mid-playback, **When** the
   person speaks, **Then** playback stops promptly, no not-yet-spoken or
   not-yet-generated sentence is spoken, and continued generation of that
   answer is abandoned.
2. **Given** an interruption, **When** the agent responds again, **Then** the
   new answer addresses the interrupting utterance and itself streams.

---

### User Story 3 - Reversibly deploy end-to-end streaming (Priority: P2)

The operator deploys the end-to-end-streaming adapter to the production
gateway via the existing gated, backed-up, one-step-reversible path;
pre-existing gateway platforms remain unaffected.

**Why this priority**: Established safety posture; the improvement has no
value until it is the running version and remains reversible.

**Independent Test**: Gated redeploy → streaming-from-generation live, both
planes listening, pre-existing platforms intact; rollback restores prior
state.

**Acceptance Scenarios**:

1. **Given** the new adapter, **When** the gated redeploy runs, **Then** each
   host-mutating step is confirmed and backed up first.
2. **Given** rollback is invoked, **Then** the gateway returns exactly to its
   pre-redeploy state.

### Edge Cases

- The agent emits its whole answer in one block (no incremental output
  available) → the system MUST still work, degrading to feature 006 behaviour
  (segment the completed reply) with no error.
- The agent streams tokens that do not yet form a complete sentence → partial
  text is buffered until a speakable unit is available; no half-sentence is
  spoken.
- The agent revises/retracts already-emitted text (if the source can do that)
  → already-spoken audio cannot be unsaid; the behaviour MUST remain coherent
  (e.g. only finalized text is spoken).
- The agent stalls mid-generation (long pause between chunks) → earlier
  sentences keep playing; the session does not wedge or falsely end the turn.
- Agent generation finishes faster than speech → remaining sentences queue and
  still play in order (feature 006 behaviour).
- Barge-in arrives while the agent is still generating → generation is
  abandoned promptly; no orphaned background agent work continues to produce
  or speak.
- Empty / tool-only answer → nothing is spoken; session returns to listening
  (unchanged).
- Agent or speech provider fails mid-stream → the turn fails perceptibly
  rather than hanging; no broken/zero-length audio.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST begin speaking the answer as soon as the first
  speakable unit is available from the agent, without waiting for the agent to
  finish composing the whole answer.
- **FR-002**: Later sentences MUST continue to be spoken in order as the agent
  produces them, with natural pacing and no audible overlap.
- **FR-003**: Incremental agent text MUST be assembled into speakable units
  before synthesis (no half-sentence audio); buffering MUST not introduce
  perceptible stalls when the agent is producing steadily.
- **FR-004**: Barge-in MUST stop playback promptly, abandon all not-yet-spoken
  and not-yet-generated content, AND stop the agent from continuing to
  generate the interrupted answer (no orphaned background generation).
- **FR-005**: If incremental agent output is unavailable, the system MUST
  gracefully fall back to feature 006 behaviour (speak the completed reply
  sentence-by-sentence) with no error and no worse than 006.
- **FR-006**: The agent loop and speech synthesis MUST remain Hermes-owned and
  reached only through the existing integration seam — no agent/STT/TTS engine
  embedded in the adapter (constitution I/IV).
- **FR-007**: Short / empty / tool-only answers MUST behave at least as well
  as feature 006 (no latency or correctness regression).
- **FR-008**: An agent or speech failure mid-stream MUST surface as a
  perceptible turn failure, not a hang or silent stall.
- **FR-009**: The change MUST be limited to how the reply is obtained
  incrementally and timed into feature 006's segmentation/playback; the media
  transport contract, signaling, control plane, and turn/state-machine
  semantics MUST remain behaviourally compatible (feature 001 fake-transport
  suite stays green).
- **FR-010**: Redeployment MUST use the existing gated, backup-first,
  one-step-reversible deploy/rollback path (reuse features 003/004 — no new
  mechanism) and MUST NOT degrade any pre-existing gateway platform.

### Key Entities *(include if feature involves data)*

- **Incremental Answer**: The agent's reply as it becomes available over time
  (a sequence of partial text increments) rather than one final string.
- **Speakable Unit**: Reused from feature 006 — a sentence-sized chunk; now
  assembled from incremental text as soon as a full unit is available.
- **Streaming Pipeline**: The produce-as-you-go flow: agent increments →
  unit assembly → per-unit synthesis → in-order playback, all overlapped.
- **Voice Session / Turn**: Reused from features 001/005/006; a turn now both
  generates and speaks concurrently.
- **Hermes Agent / TTS**: Reused; the agent now feeds text incrementally and
  the interrupt path stops its generation.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For an answer whose full composition takes the agent ≥10 s, the
  first audible sentence is heard within 3 seconds of the turn starting to be
  answered (vs after full composition today).
- **SC-002**: For a long answer, total time-to-first-word is reduced by at
  least 60% compared with feature 006 on the same prompt.
- **SC-003**: Sentences play in order with no perceptible mid-answer silence
  gap longer than ~1.5 s while the agent is producing steadily, and no
  overlap/garble.
- **SC-004**: Barge-in during a still-generating answer stops audio within
  300 ms, zero not-yet-spoken sentences are spoken, and continued agent
  generation of that answer ceases within 1 s.
- **SC-005**: Short / empty / tool-only answers show no latency or correctness
  regression vs feature 006; when incremental output is unavailable the system
  is no worse than feature 006.
- **SC-006**: A long multi-sentence answer is fully intelligible and coherent
  end to end (a listener understands it without replays; no missing or
  duplicated sentences vs the agent's actual answer).
- **SC-007**: Feature 001's fake-transport conversation suite remains 100%
  green after this change.
- **SC-008**: 0 regressions to pre-existing gateway platforms after redeploy;
  rollback restores the exact pre-redeploy state in under 5 minutes.

## Assumptions

- The user-visible goal is "hear the answer begin while the agent is still
  composing it." Whether the Hermes integration can surface **incremental**
  agent output to the adapter (a streaming/partial path rather than the single
  final reply consumed today) is a capability that **planning Phase 0 must
  confirm**; this spec defines the outcome and a mandatory graceful fallback
  to feature 006 if incremental output is not available (FR-005), so the
  feature is never worse than 006 regardless of that finding.
- Sentence assembly/segmentation is text orchestration only (reuses feature
  006's segmentation); STT, the agent loop, and TTS remain Hermes-owned via
  the existing seam (constitution I/IV).
- Feature 006's per-sentence pipelined synthesis + incremental playback and
  feature 005's media transport are reused unchanged; only the reply *source*
  becomes incremental and the interrupt path also cancels agent generation.
- The interrupt path must cancel in-flight agent generation, not just
  playback (FR-004) — extending feature 006's barge-in, which only abandoned
  synthesis/playback.
- Redeploy reuses features 003/004 `deploy/deploy-to-hermes.sh` /
  `rollback.sh`; the both-planes post-verify and the documented deploy-gate
  invocation quirk (feed confirmation on stdin) still apply.
- Real end-to-end streaming behaviour is proven by the host-side live spoken
  test (a human at a microphone), consistent with constitution V; the
  fake-transport suite guards the unchanged conversation logic.
- LAN/SSH-forward posture is unchanged; the live client connects to the
  gateway's LAN address directly. TTS text normalization (emoji/markdown) and
  STT model choice remain out of scope (separate concerns).
