# Feature Specification: Streaming Spoken Replies (sentence-by-sentence)

**Feature Branch**: `006-streaming-tts`
**Created**: 2026-05-19
**Status**: Draft
**Input**: User description: "currently the tts response from hermes agent is
not streamed its send after hermes is finished speaking i need the streaming
response as a natural conversation sentence by sentence"

## Overview

Feature 005 made real audio flow end-to-end, but the reply is delivered as a
single block: the gateway waits for the **entire** agent answer, synthesizes
the **whole** thing to one audio clip, then plays it. For anything longer than
a short sentence this feels unnatural — multi-second dead air, then a long
monologue that can't be reacted to until it finishes. Live testing confirmed
this directly (a long reply produced ~10 s of silence then a 30–60 s
uninterrupted clip).

This feature makes the spoken reply **stream as natural conversation**: the
caller starts hearing the answer almost immediately, sentence by sentence,
while the rest is still being produced — the way a person speaks. It changes
only how the reply is segmented, synthesized, and played back over the
existing media path; the conversation logic boundaries, the Hermes
STT/agent/TTS integration seam, and the media transport contract are reused.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The reply starts speaking almost immediately (Priority: P1)

A person asks a question that has a multi-sentence answer. Instead of waiting
in silence for the whole answer to be composed and synthesized, they hear the
first sentence quickly and the following sentences continue smoothly after it.

**Why this priority**: This is the entire point — turning a "wait… monologue"
into a natural conversational reply. Without it the assistant feels broken for
any non-trivial answer.

**Independent Test**: Ask a question with a known multi-sentence answer; the
first audible words begin within a short conversational delay, well before the
full answer could have been synthesized.

**Acceptance Scenarios**:

1. **Given** the agent produces a multi-sentence reply, **When** it is spoken
   back, **Then** the first sentence is heard within a short conversational
   delay (not after the whole reply is composed).
2. **Given** a long reply, **When** it plays, **Then** sentences follow one
   another with natural pacing and no large mid-reply gaps or audible seams.
3. **Given** a one-word / single-short-sentence reply, **When** it is spoken,
   **Then** behaviour is at least as fast as before (no regression for short
   replies).

---

### User Story 2 - Barge-in still works during a streaming reply (Priority: P1)

While the streamed reply is still playing (and possibly still being produced),
the person talks over it. Playback stops promptly, anything not yet spoken is
abandoned, and their new utterance becomes the next turn.

**Why this priority**: Streaming must not regress the barge-in behaviour
proven in feature 005; interrupting a long streamed answer is exactly when
barge-in matters most.

**Independent Test**: During a streaming multi-sentence reply, speak; playback
stops promptly and the not-yet-played sentences are not spoken afterwards.

**Acceptance Scenarios**:

1. **Given** a streaming reply is mid-playback, **When** the person speaks,
   **Then** audio stops promptly and no further (already-queued or
   not-yet-synthesized) sentences are played.
2. **Given** an interruption, **When** the agent responds again, **Then** the
   new response addresses the interrupting utterance and itself streams.

---

### User Story 3 - Reversibly deploy the streaming reply (Priority: P2)

The operator deploys the streaming-capable adapter to the production gateway
using the existing gated, backed-up, one-step-reversible path; pre-existing
gateway platforms remain unaffected.

**Why this priority**: Established safety posture; the improvement has no value
until it is the running version and remains reversible.

**Independent Test**: Gated redeploy → streaming reply live, both planes
listening, pre-existing platforms intact; rollback restores prior state.

**Acceptance Scenarios**:

1. **Given** the streaming adapter, **When** the gated redeploy runs, **Then**
   each host-mutating step is confirmed and backed up first.
2. **Given** rollback is invoked, **Then** the gateway returns exactly to its
   pre-redeploy state.

### Edge Cases

- Reply is a single short sentence → spoken as one chunk, no worse than today.
- Reply has no sentence punctuation (one long run-on) → still chunked into
  natural speakable units so playback can begin early (no waiting for the end).
- A sentence chunk fails to synthesize → it is skipped/handled without aborting
  the rest of the reply or wedging the session.
- Barge-in arrives between sentences → no "orphan" sentence plays after the
  interruption; the transport is left usable for the next turn.
- Reply is empty / tool-only → nothing is spoken; session returns to listening
  (unchanged from today).
- Sentences are produced faster than they can be spoken → later sentences wait
  their turn and still play in order, with no overlap or dropouts.
- Sentence segmentation must not split mid-number/abbreviation so audibly that
  the reply becomes unintelligible.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The spoken reply MUST begin playing after only the first
  speakable unit is ready, not after the entire reply is composed.
- **FR-002**: The reply MUST be segmented into natural speakable units
  (sentence-sized) and spoken in order with natural pacing and no audible
  gaps/overlap between units.
- **FR-003**: Synthesis of later units MUST overlap playback of earlier units
  (pipelined) so the caller is not waiting between sentences.
- **FR-004**: Barge-in MUST stop playback promptly AND abandon all
  not-yet-played and not-yet-synthesized units; the transport stays usable for
  the next turn (no regression vs feature 005).
- **FR-005**: Synthesis and playback MUST be reached only through the existing
  Hermes integration seam — no STT/TTS/agent engine is embedded in the
  adapter; provider/voice selection stays Hermes-owned (constitution I/IV).
- **FR-006**: Short/empty/tool-only replies MUST behave at least as well as
  today (no latency regression, no broken/zero-length audio).
- **FR-007**: A unit that fails to synthesize MUST NOT abort the remaining
  reply or wedge the session.
- **FR-008**: The change MUST be limited to reply segmentation, synthesis
  pipelining, and incremental playback; the WebRTC media transport contract,
  signaling, control plane, and turn/state machine semantics MUST remain
  behaviourally compatible (feature 001 fake-transport suite stays green).
- **FR-009**: Redeployment MUST use the existing gated, backup-first,
  one-step-reversible deploy/rollback path (reuse features 003/004 — no new
  mechanism).
- **FR-010**: Redeployment MUST NOT degrade or remove any pre-existing gateway
  platform or capability.

### Key Entities *(include if feature involves data)*

- **Reply Stream**: The agent's answer as an ordered series of speakable units
  rather than one block.
- **Speakable Unit**: A sentence-sized chunk of reply text that is
  individually synthesized and played in order.
- **Synthesis Pipeline**: The ordered, overlapped produce-synthesize-play flow
  that keeps audio continuous while later units are still being synthesized.
- **Voice Session / Turn**: Reused from feature 001/005; a turn now emits a
  streamed reply instead of a single clip.
- **Hermes Agent / TTS**: Reused; produce the reply text and synthesize each
  unit (unchanged integration seam).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a multi-sentence reply, the first audible words begin within
  1.5 seconds of the reply being ready to speak (vs after full-reply
  synthesis today).
- **SC-002**: Sentences play in order with no perceptible mid-reply silence
  gap longer than ~1 second and no overlap/garble between sentences.
- **SC-003**: Barge-in during a streamed reply stops audio within 300 ms and
  zero not-yet-played sentences are spoken afterwards.
- **SC-004**: A 5+-sentence reply is fully intelligible and natural-sounding
  end to end (a listener understands it without replays).
- **SC-005**: Short (≤1 sentence) and empty/tool-only replies show no latency
  or correctness regression vs feature 005.
- **SC-006**: Feature 001's fake-transport conversation test suite remains
  100% green after this change.
- **SC-007**: 0 regressions to pre-existing gateway platforms after redeploy;
  rollback restores the exact pre-redeploy state in under 5 minutes.

## Assumptions

- "Streaming, sentence by sentence" means the **caller's experience** is
  incremental speech; it is delivered by segmenting the reply into speakable
  units and pipelining per-unit synthesis + playback over the existing media
  transport. If the Hermes integration exposes incremental/partial reply text,
  units are emitted as text arrives; otherwise the completed reply text is
  segmented and pipelined — both deliver the sentence-cadence experience and
  the same user-visible success criteria.
- Sentence segmentation is text chunking/orchestration only (no ASR/TTS/agent
  reasoning); STT, the agent loop, and TTS remain Hermes-owned via the
  existing seam (constitution I).
- The media transport, signaling, control plane, and conversation/turn state
  machine from features 001/005 are reused; only reply
  segmentation/synthesis/playback changes (FR-008).
- Redeploy reuses features 003/004 `deploy/deploy-to-hermes.sh` /
  `rollback.sh`; the both-planes post-verify still applies; the documented
  deploy-gate invocation quirk (feed confirmation on stdin) still applies.
- Real streaming quality is proven by the host-side live spoken test (a human
  at a microphone), consistent with constitution V; the fake-transport suite
  guards the unchanged conversation logic.
- LAN/SSH-forward posture and deferred port auth are unchanged and out of
  scope here; the live client connects to the gateway's LAN address directly.
- TTS text normalization (e.g., emoji/markdown spoken aloud) is a separate,
  explicitly out-of-scope concern (user chose to leave it as-is); this feature
  only changes timing/segmentation, not text cleanup.
