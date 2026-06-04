# Feature Specification: Opus upstream (mic → STT) voice

**Feature Branch**: `025-upstream-opus-stt`
**Created**: 2026-06-04
**Status**: Draft
**Input**: User description: "add support for opus for upstream voice to stt in gateway and in sdks"

## Context (non-normative)

On the gRPC voice plane a satellite currently sends its **microphone audio
upstream as raw 16 kHz PCM** (the device→gateway path), while the gateway runs
speech-to-text (STT) on it. Feature 024 added full-band **Opus on the
downstream** (gateway→device) path; this feature adds the symmetric option on
the **upstream** path: a satellite can compress its mic audio with Opus instead
of streaming raw PCM, and the gateway decodes that Opus back to audio before
speech recognition.

Why this matters:

- **Uplink bandwidth.** Raw 16 kHz PCM is ~256 kbit/s continuously while the mic
  is open; Opus carries the same speech at roughly a tenth of that. On
  bandwidth-constrained or shared wireless links (the common satellite
  deployment), that is a large, continuous saving on the upload direction.
- **Consistency.** WebRTC satellites already send Opus upstream; the gRPC native
  path is the one still sending raw PCM. This closes that gap so both directions
  of the gRPC plane can use Opus, negotiated the same way the downstream codec
  already is.

The recognized text and the gateway's STT quality must be unchanged — Opus is
transparent for speech — and raw PCM upstream must remain the default and
fallback so existing satellites and devices that cannot encode Opus keep
working.

## Clarifications

### Session 2026-06-04

- Q: Wire shape for upstream Opus? → A: Add an **additive Opus mic arm** to
  `ClientFrame` in `proto/aivg/satellite/v1/audio.proto` (a new oneof arm
  alongside `pcm`), and regenerate the **C++ and Python** bindings. No existing
  field changes meaning.
- Q: At what rate does the device encode upstream Opus, and what happens to the
  current mic decimation? → A: The C++ SDK's `GrpcTransport::send_mic` **encodes
  Opus at 48 kHz** (the capture/native rate) instead of decimating to 16 kHz —
  i.e. the gRPC mic boundary moves to 48 kHz and the 48→16 mic downsample
  (`mic_down`) is dropped from the Opus path.
- Q: How does the gateway turn the Opus mic arm into STT input? → A: The gRPC
  handler **decodes the Opus mic arm → 48 kHz PCM → resamples to 16 kHz → STT**
  (so STT receives the 16 kHz audio it expects; the decode/resample is
  gateway-side).
- Q: At the 48 kHz mic boundary, how is the 16 kHz PCM upstream fallback
  produced (since "drop mic_down" conflicts with keeping PCM)? → A:
  **Negotiation-dependent capture rate** — the device captures at **48 kHz when
  the Opus mic arm is negotiated** and at **16 kHz when falling back to PCM**;
  **no on-device resampler** in either case (`mic_down` is dropped entirely). The
  mic frame size is therefore per-session, set once the upstream codec is agreed.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A satellite streams Opus mic audio and is transcribed correctly (Priority: P1)

A native satellite negotiates to send its microphone audio upstream as Opus. It
captures speech, encodes it, and streams it to the gateway. The gateway decodes
the Opus back to audio and recognizes the speech, producing the same transcript
it would have produced from raw PCM — at a fraction of the upload bandwidth.

**Why this priority**: This is the feature — letting the device compress the
mic uplink with no loss of recognition quality. Without it there is nothing to
ship.

**Independent Test**: Speak a known phrase into a satellite configured for Opus
upstream; confirm the gateway transcribes it to the same text as the raw-PCM
path, and that the bytes uploaded for that utterance are materially smaller than
the equivalent raw-PCM upload.

**Acceptance Scenarios**:

1. **Given** a satellite negotiated for Opus upstream, **When** the user speaks a
   phrase, **Then** the gateway produces a transcript equivalent to the raw-PCM
   path for the same speech.
2. **Given** the same spoken utterance sent as Opus vs. as raw PCM, **When** both
   are uploaded, **Then** the Opus upload is materially smaller (target ≥ ~5×
   fewer bytes) for equivalent recognized text.
3. **Given** an Opus upstream session, **When** end-of-utterance is signaled,
   **Then** recognition completes and the turn proceeds exactly as it does today
   (agent reply, downstream audio, events all unaffected).

---

### User Story 2 - Existing raw-PCM satellites are unaffected (Priority: P1)

A satellite that does not negotiate Opus upstream — including every satellite
built before this feature, and devices that cannot encode Opus — continues to
send raw 16 kHz PCM and is transcribed exactly as today. No device-side change
is required to keep working.

**Why this priority**: Backward compatibility is non-negotiable. The upstream
contract and all existing satellites must keep working unchanged; a device that
can't (or won't) encode Opus must never be forced to. Co-P1 with US1.

**Independent Test**: Run a satellite that advertises no upstream codec (or only
PCM); confirm it streams raw 16 kHz PCM and is transcribed identically to
pre-feature behavior, with no errors.

**Acceptance Scenarios**:

1. **Given** a device that advertises no upstream codec, **When** it speaks,
   **Then** it streams raw 16 kHz PCM and is transcribed as today.
2. **Given** a pre-existing satellite with no knowledge of this feature, **When**
   it connects to the upgraded gateway, **Then** it operates exactly as before
   with no reconfiguration.
3. **Given** the upgraded gateway, **When** any mix of Opus-upstream and
   PCM-upstream satellites connect, **Then** each is handled correctly with no
   cross-effect.

---

### User Story 3 - Robust negotiation and graceful fallback (Priority: P2)

A satellite advertises Opus upstream but the gateway (or a particular
deployment) cannot accept it, or the reverse. Negotiation resolves to a mode
both sides support — falling back to raw PCM — and the session works: no
silence, no crash, no garbled recognition. The device knows which mode is in
effect and streams accordingly.

**Why this priority**: Safe rollout across mixed gateway/device versions
requires that an unsupported upstream codec never strands a device. Important,
but secondary to the core path (US1) and protecting existing devices (US2).

**Independent Test**: Pair an Opus-advertising device with a gateway that does
not accept Opus upstream (and vice versa); confirm the session falls back to raw
PCM and transcription still works.

**Acceptance Scenarios**:

1. **Given** a device that advertises Opus upstream and a gateway that cannot
   accept it, **When** the session starts, **Then** both fall back to raw PCM and
   transcription works.
2. **Given** the negotiation outcome, **When** the device begins streaming mic
   audio, **Then** it sends the agreed format and the gateway interprets it
   correctly (the device never has to guess).
3. **Given** a malformed or undecodable upstream Opus frame, **When** it arrives,
   **Then** the gateway drops it without crashing the session and recognition
   continues for the rest of the utterance.

---

### Edge Cases

- **Device cannot encode Opus** (e.g. a very constrained MCU): it simply does not
  advertise Opus upstream and streams raw PCM — never forced to encode.
- **Mixed-version fleet**: an old gateway ignores an unknown upstream-codec
  preference and receives raw PCM; a new gateway serving an old device receives
  raw PCM. Neither errors.
- **STT operating rate**: recognition quality must not regress regardless of the
  rate the device captured/encoded at; the gateway delivers decoded audio to STT
  in the form STT expects.
- **Endpointing / VAD unaffected**: wake, end-of-utterance, and barge-in continue
  to work identically; server-side endpointing still runs on the decoded audio.
- **Upstream only**: this feature changes the device→gateway (mic) path only; the
  downstream (gateway→device) path is unchanged (feature 024 already covers it).
- **Packet loss / partial frames**: a dropped or corrupt upstream frame degrades
  gracefully (a small audio gap) rather than failing the turn.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A satellite MUST be able to advertise, at session setup, that it
  will send its upstream mic audio as Opus (in addition to the existing raw-PCM
  option), best-first like the downstream-codec preference.
- **FR-002**: The gateway MUST accept the Opus mic arm when negotiated, decode it
  to 48 kHz audio, resample that to 16 kHz, and feed it to speech recognition,
  producing transcripts equivalent to the raw-PCM path for the same speech.
- **FR-003**: Recognition quality MUST NOT regress when Opus upstream is used
  versus raw PCM (Opus is transparent for voice); the recognized text MUST be
  equivalent for the same spoken input.
- **FR-004**: Raw 16 kHz PCM upstream MUST remain the default and the guaranteed
  fallback; a device that advertises nothing (or only PCM) streams raw PCM and is
  unaffected.
- **FR-005**: The change MUST be backward-compatible and additive: existing
  satellites, the existing raw-PCM upstream path, and the existing wire contract
  keep working with no device-side change and no reconfiguration.
- **FR-006**: When the two sides cannot agree on Opus upstream, negotiation MUST
  fall back to raw PCM; the session MUST still work (no silence, crash, or
  garbled recognition), and the agreed mode MUST be unambiguous to both sides.
- **FR-007**: A malformed/undecodable upstream Opus frame MUST be dropped without
  terminating the session; recognition continues for the remainder of the
  utterance.
- **FR-008**: The SDKs MUST let a device choose Opus upstream (where it has the
  capability), and MUST keep raw PCM available; a device that cannot encode Opus
  MUST be able to opt out / not advertise it.
- **FR-009**: This feature MUST be limited to the upstream (device→gateway / mic)
  path; the downstream path and the agent/TTS/turn flow MUST be unchanged.
- **FR-010**: Endpointing (wake, end-of-utterance, barge-in) and server-side
  silence detection MUST continue to work identically on the decoded upstream
  audio.
- **FR-011**: An Opus upstream upload for a given utterance MUST be materially
  smaller than the equivalent raw-PCM upload (the bandwidth benefit), with no
  loss of recognized text.
- **FR-012**: The device MUST capture at the **negotiated upstream rate** — 48 kHz
  when the Opus mic arm is in effect, 16 kHz on the PCM fallback — and MUST NOT
  resample mic audio on-device (no `mic_down`). The device MUST therefore learn
  the negotiated upstream codec before it begins streaming mic audio.

### Key Entities *(include if feature involves data)*

- **Upstream codec preference**: the device's advertised, best-first choice for
  the mic→gateway path (raw PCM and/or Opus), declared at session setup —
  symmetric to the existing downstream-codec preference.
- **Upstream mic frame**: a unit of device→gateway audio, either raw PCM (today)
  or Opus (this feature); the gateway decodes Opus before recognition.
- **Negotiated upstream mode**: the format both sides agreed to send/expect for
  the mic path; raw PCM is the universal fallback.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For an Opus-upstream session, the gateway transcribes a known set
  of spoken phrases to text equivalent to the raw-PCM path (no measurable
  word-error increase attributable to the codec).
- **SC-002**: An Opus-upstream utterance uploads at least ~5× fewer bytes than the
  same utterance as raw 16 kHz PCM, for equivalent recognized text.
- **SC-003**: 100% of sessions where the device sends no upstream-codec preference
  (or only PCM) stream raw 16 kHz PCM and transcribe identically to pre-feature
  behavior.
- **SC-004**: 100% of mismatched-capability pairings fall back to raw PCM and
  still transcribe successfully (no silence, crash, or garbled recognition).
- **SC-005**: Existing satellites require **no** code or config change to keep
  working after the gateway/SDK upgrade.
- **SC-006**: Malformed upstream Opus frames cause at most a localized audio gap,
  never a session/turn failure, across a fault-injection test pass.
- **SC-007**: Wake / end-of-utterance / barge-in behave identically with Opus
  upstream as with raw PCM across the test scenarios.

## Assumptions

- The upstream contract is extended **additively** (a new negotiated upstream
  codec + an Opus-carrying mic frame), mirroring the existing downstream-codec
  negotiation; no existing field changes meaning, so old↔new interoperate on raw
  PCM.
- The primary target is the **gRPC native tier** (the path still sending raw PCM)
  and its **C++ SDK**, which already has Opus encode/decode capability. **WebRTC
  satellites already send Opus upstream** (out of scope), and the **ESPHome**
  path streams the rate Home Assistant provides (out of scope unless trivial).
- Speech recognition is transparent to Opus: decoding Opus to the audio STT
  expects yields equivalent transcripts; STT continues to run at whatever rate it
  already uses (the gateway delivers decoded audio in that form).
- Opus encode on the device targets the native gRPC tier (RPi-class), which has
  ample CPU; very constrained devices simply don't advertise Opus upstream.
- The device encodes Opus at **48 kHz** (its capture/native rate, the same rate
  the downstream uses) rather than decimating to 16 kHz on-device; the gateway
  decodes to 48 kHz then resamples to 16 kHz for STT (clarified 2026-06-04). The
  gRPC mic capture rate is **per-session**: 48 kHz when the Opus arm is
  negotiated, 16 kHz on PCM fallback — **no on-device resampler** in either case.
  The device must learn the negotiated upstream codec before it starts streaming
  mic audio (the negotiation/handshake mechanism is a planning detail).
- The bandwidth benefit (SC-002) is the main motivation; STT receives 16 kHz
  either way, so quality is unchanged — the win is the compressed uplink.
- The change composes with feature 024 (downstream Opus): a session may use Opus
  in one or both directions, negotiated independently per direction.

## Dependencies

- The existing gRPC upstream mic path (raw `PcmChunk` frames) and the gateway's
  inbound-audio → STT flow that this extends.
- The existing downstream-codec negotiation pattern (best-first preference at
  session setup) that the upstream negotiation mirrors.
- The SDKs' existing Opus capability (used today for the WebRTC/downstream paths)
  reused for upstream encode.

## Out of Scope

- The downstream (gateway→device) path — already handled by feature 024.
- WebRTC satellites' upstream (already Opus).
- Forcing Opus on devices that cannot encode it; raw PCM remains universal.
- The agent loop, TTS, and turn lifecycle — unchanged.
- ESPHome upstream codec changes (the device streams Home Assistant's format),
  beyond noting it is unaffected.
- Changing what STT engine is used or how it is configured beyond feeding it the
  decoded upstream audio.
