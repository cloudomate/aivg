# Feature Specification: gRPC downstream TTS decode to canonical 48 kHz PCM

**Feature Branch**: `023-grpc-tts-pcm-decode`
**Created**: 2026-06-03
**Status**: Draft
**Input**: User description: "In transports/grpc/media_adapter.py, GrpcMediaAdapter.send_audio (or the outbound pump) must decode the TTS bytes to 48 kHz s16le mono PCM before queuing — i.e. mirror what webrtc/signaling.py:send_audio already does with av.open + AudioResampler(format=\"s16\", layout=\"mono\", rate=48000). Once self._out holds real 48 kHz PCM, the existing 48→16 downsample + the client's 16→48 upsample are both correct and audio will be clean. This is a message from the agent building the gRPC-based client; we need to add this in the gateway."

## Context (non-normative)

The gateway hands every voice transport the **raw, provider-encoded TTS clip**
(whatever container/sample-rate the speech provider produced — e.g. a WAV/MP3/
Opus blob) via the shared `send_audio(bytes)` seam. Each transport is
responsible for turning that clip into the canonical internal audio
representation (48 kHz signed-16-bit little-endian mono PCM) before it travels
its wire.

The WebRTC transport already does this: it decodes the clip and resamples it to
48 kHz mono PCM, then frames it for its outbound track. The gRPC transport
**does not** — it queues the raw encoded bytes as if they were already 48 kHz
PCM. The gRPC downstream path then runs its standard 48 kHz→16 kHz downsample
over those bytes, and the gRPC client runs a 16 kHz→48 kHz upsample on receipt.
Because the bytes were never actually 48 kHz PCM, both resample steps operate on
garbage and the satellite plays back noise/distortion instead of speech.

The fix is to give the gRPC transport the same decode-and-resample-to-48 kHz
step the WebRTC transport already has, so the existing downstream resampling
(gateway 48→16, client 16→48) becomes correct end-to-end. This closes the
gateway half of the gRPC audio plane that the recently-shipped client-side
48↔16 kHz resampling (the C++ SDK fix) depends on.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Clean spoken replies on a gRPC satellite (Priority: P1)

An end user speaks to a satellite that connects to the gateway over the gRPC
transport. The gateway recognizes the speech, the agent responds, and the
gateway synthesizes the reply. The user hears the reply played back on the
satellite's speaker as clear, natural speech at the correct pitch and speed —
identical in quality to the same satellite running over the WebRTC transport.

**Why this priority**: This is the entire feature. Without it, every spoken
reply over the gRPC transport is unintelligible, which makes the gRPC audio
plane unusable for real devices. It is the gateway counterpart that the
client-side resampling already assumes is in place.

**Independent Test**: Drive a full voice turn over the gRPC transport against a
speech provider whose synthesized clip is NOT already 48 kHz s16le mono PCM
(i.e. a normal provider clip in its native container/rate). Capture the audio
the satellite receives and confirm it reconstructs the intended speech (correct
duration, pitch, and intelligibility) rather than noise.

**Acceptance Scenarios**:

1. **Given** a gRPC-connected satellite and a synthesized reply in the speech
   provider's native container/sample-rate, **When** the turn completes,
   **Then** the satellite plays back intelligible speech at correct pitch and
   duration.
2. **Given** the same synthesized reply delivered once over WebRTC and once over
   gRPC, **When** both are played back, **Then** the two are perceptually
   equivalent (no added noise, no pitch/speed shift on the gRPC path).
3. **Given** a synthesized reply whose source sample-rate differs from 48 kHz,
   **When** it is sent over gRPC, **Then** the reply is resampled so its
   playback duration and pitch are preserved (no fast/slow/"chipmunk" effect).

---

### User Story 2 - Graceful handling of empty / undecodable clips (Priority: P2)

The gateway sometimes hands the transport an empty clip, an internal sentinel
marker (e.g. a "providers unavailable" placeholder), or bytes that cannot be
decoded as audio. On the gRPC transport these must be handled the same way the
WebRTC transport handles them: silently produce no audio and keep the session
alive, never crash the stream or emit a burst of noise.

**Why this priority**: Tool-only turns, error sentinels, and provider hiccups
occur in normal operation. A satellite must not drop its session or blast noise
because a particular turn produced nothing playable.

**Independent Test**: Send an empty payload, a short non-audio sentinel, and a
deliberately corrupt clip over the gRPC transport; confirm each results in no
audio frames emitted, no exception that ends the stream, and a still-usable
session for the next turn.

**Acceptance Scenarios**:

1. **Given** an empty or sub-minimal payload, **When** it is sent over gRPC,
   **Then** no audio frames are emitted and the session remains open.
2. **Given** an undecodable clip, **When** it is sent over gRPC, **Then** it is
   dropped without emitting audio and without terminating the stream.
3. **Given** a turn that produces no speech (tool-only), **When** the turn
   completes, **Then** the satellite plays nothing and is ready for the next
   turn.

---

### User Story 3 - Barge-in and streaming pipelining still work (Priority: P3)

A user interrupts the satellite while it is speaking, or the gateway streams a
reply sentence-by-sentence. The decode step must not break the existing
behaviors that depend on the outbound audio path: barge-in promptly stops
playback, and per-sentence/streaming synthesis still flows frame-by-frame.

**Why this priority**: Barge-in and streaming pipelining are existing, working
behaviors of the voice plane. The decode change sits directly on the outbound
audio path, so it must preserve them rather than regress them.

**Independent Test**: Over gRPC, start a long reply and trigger barge-in
mid-playback; confirm playback stops promptly. Separately, drive a streamed
multi-sentence reply and confirm the satellite plays the full reply without gaps
or truncation.

**Acceptance Scenarios**:

1. **Given** audio playing over gRPC, **When** the user barges in, **Then**
   queued/unplayed audio is dropped and playback stops promptly.
2. **Given** a streamed multi-unit reply over gRPC, **When** it is synthesized
   unit-by-unit, **Then** the satellite plays the complete reply in order.

---

### Edge Cases

- **Source rate ≠ 48 kHz**: provider clips at 22.05 kHz, 24 kHz, 44.1 kHz, etc.
  must be resampled to 48 kHz mono so pitch/duration are preserved before the
  downstream 48→16 step.
- **Multi-channel source**: a stereo source must be downmixed to mono.
- **Undecodable / sentinel bytes**: dropped silently, session preserved (see US2).
- **Partial decode failure**: if decoding aborts partway, already-decoded audio
  is still delivered and the session is not killed.
- **Frame-boundary continuity across multiple clips in one turn**: streamed
  per-sentence clips must not introduce clicks or rate discontinuities at the
  seams (the downstream resampler state must stay consistent).
- **Internal-only contract**: this changes gateway-internal behavior only; the
  satellite wire contract and the format of bytes a satellite receives (16 kHz
  downstream) are unchanged — only their correctness improves.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The gRPC transport MUST decode each downstream TTS clip from its
  provider-supplied container/encoding into raw signed-16-bit little-endian
  mono PCM before that audio enters the gRPC downstream resampling path.
- **FR-002**: The gRPC transport MUST resample decoded downstream audio to the
  canonical internal sample rate of 48 kHz (mono) so that the existing
  48 kHz→16 kHz downstream downsample operates on true 48 kHz PCM.
- **FR-003**: The gRPC transport's downstream decode/resample behavior MUST be
  functionally equivalent to the WebRTC transport's existing decode/resample
  behavior for the same input clip (same canonical format: s16 mono 48 kHz).
- **FR-004**: The audio delivered to the satellite MUST preserve the original
  speech's pitch and duration (no speed/pitch distortion introduced by rate
  mismatch).
- **FR-005**: The gRPC transport MUST treat empty payloads and sub-minimal /
  non-audio sentinel markers as "emit nothing", producing no audio frames and
  keeping the session open.
- **FR-006**: The gRPC transport MUST handle undecodable input by dropping it
  without emitting audio and without terminating or crashing the gRPC stream or
  the voice session.
- **FR-007**: A decode error that occurs partway through a clip MUST NOT end the
  session; any audio already decoded MAY still be delivered.
- **FR-008**: The change MUST NOT alter the satellite-facing wire contract: the
  downstream codec/sample-rate the satellite negotiates and receives (16 kHz)
  and the gRPC message schema remain unchanged; only the correctness of the
  audio content changes.
- **FR-009**: Existing outbound-path behaviors MUST be preserved: barge-in
  (prompt stop of queued/unplayed audio) and streaming/per-unit synthesis
  pipelining continue to work over gRPC.
- **FR-010**: Multi-channel source audio MUST be downmixed to mono as part of
  the conversion.
- **FR-011**: The decode/resample step MUST NOT block or stall the gRPC response
  stream such that unrelated downstream frames (turn lifecycle events,
  transcripts) are delayed beyond their existing behavior.

### Key Entities *(include if feature involves data)*

- **TTS clip (downstream)**: the provider-encoded reply audio handed to the
  transport; arbitrary container/codec/sample-rate/channel-count.
- **Canonical internal PCM**: signed-16-bit little-endian mono PCM at 48 kHz —
  the format all transports normalize to before their wire-specific encoding.
- **gRPC downstream frame**: the audio the satellite receives over gRPC
  (16 kHz), produced by downsampling the canonical 48 kHz PCM; its schema and
  rate are unchanged by this feature.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of voice turns over the gRPC transport that produce a spoken
  reply play back as intelligible speech (no noise/distortion), where previously
  they were unintelligible.
- **SC-002**: Spoken replies delivered over gRPC are perceptually equivalent to
  the same replies delivered over WebRTC (no added noise, no pitch or speed
  shift), confirmed across at least one provider clip whose native rate is not
  48 kHz.
- **SC-003**: Playback duration of a gRPC reply matches the intended clip
  duration within a small tolerance (e.g. ≤ 5%), confirming no rate-mismatch
  speed error.
- **SC-004**: Empty clips, sentinel markers, and undecodable input over gRPC
  result in zero emitted audio frames and zero session terminations across a
  test pass.
- **SC-005**: Barge-in over gRPC stops playback promptly (queued/unplayed audio
  is dropped) and streamed multi-sentence replies play in full — no regression
  from current behavior.
- **SC-006**: No change is required on the satellite/client side and no change
  to the wire contract to obtain clean audio (the fix is entirely gateway-side).

## Assumptions

- The canonical internal audio representation is 48 kHz signed-16-bit
  little-endian mono PCM, matching the WebRTC transport and the internal voice
  pipeline; the satellite-facing gRPC wire remains 16 kHz.
- The gateway already hands each transport the raw provider-encoded TTS clip via
  the shared `send_audio(bytes)` seam (i.e. decode responsibility legitimately
  belongs in the transport, as it does for WebRTC today).
- The audio decoding/resampling capability the WebRTC transport uses is
  available to the gRPC transport in the same runtime environment.
- **Scope is the gRPC transport only.** The esphome transport appears to share
  the same "queue raw bytes" shape; whether it needs the identical fix is
  **out of scope** for this feature and tracked separately (it may have a
  different downstream audio source or already be exercised only with PCM).
- The existing downstream resampling on both sides (gateway 48→16, client
  16→48) is correct once the input to it is genuinely 48 kHz PCM, per the
  originating report; this feature does not change those resamplers.
- The client-side gRPC 48↔16 kHz resampling (C++ SDK) is already in place and
  depends on this gateway-side fix to produce clean end-to-end audio.

## Dependencies

- The shared `send_audio(bytes)` transport seam and the gRPC downstream audio
  path (downsample + frame + encode) that this decode step feeds into.
- The same audio decode/resample facility relied on by the WebRTC transport.

## Out of Scope

- Any change to the satellite/client SDKs or the gRPC/satellite wire contract.
- Applying the same decode fix to the esphome transport (tracked separately).
- Changing the downstream wire sample rate (remains 16 kHz) or the negotiated
  downstream codec set.
- On-device/client-side audio handling (already addressed by the client fix).
