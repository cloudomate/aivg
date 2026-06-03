# Feature Specification: Negotiated downstream PCM sample rate (gRPC)

**Feature Branch**: `024-downstream-rate-negotiation`
**Created**: 2026-06-03
**Status**: Draft
**Input**: User description: "Let a native gRPC satellite negotiate the sample rate of the downstream (gateway→device) PCM audio, instead of the gateway always emitting a fixed 16 kHz. A client whose audio boundary runs at 48 kHz (e.g. rpi-pipewire) advertises that rate; the gateway honors it and sends 48 kHz PCM directly. This removes the lossy, bug-prone 48 kHz → 16 kHz → 48 kHz double-resample currently in the path."

## Context (non-normative)

The gateway's internal voice pipeline runs at **48 kHz**. On the gRPC voice
plane, the downstream (gateway→device) PCM audio is currently always emitted at
a **fixed 16 kHz**: the gateway downsamples its 48 kHz audio to 16 kHz for the
wire, and a 48 kHz-native device (e.g. the rpi-pipewire reference satellite, and
the C++ SDK whose audio callback boundary is 48 kHz) then upsamples 16 kHz back
to 48 kHz to play it.

That round trip — **48 kHz → 16 kHz (gateway) → 48 kHz (device)** — throws away
the upper half of the audio band and adds two resampling stages whose mismatch
was the source of recent audio defects. For a device that already runs at
48 kHz, both resamples are pure loss with no benefit: the gateway *has* 48 kHz
audio and the device *wants* 48 kHz audio, yet the wire forces a 16 kHz
bottleneck between them.

This feature lets a native gRPC satellite **advertise the downstream PCM sample
rate it wants**, and lets the gateway **honor it** when it can produce that rate
— sending 48 kHz PCM straight through with no resampling. Devices that don't
advertise (or only support 16 kHz) keep getting 16 kHz exactly as today, so the
change is backward-compatible and additive.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A 48 kHz device gets full-band, resample-free playback (Priority: P1)

A native satellite whose audio path runs at 48 kHz (e.g. rpi-pipewire) connects
over gRPC and advertises that it wants 48 kHz downstream PCM. The gateway sends
its reply audio at 48 kHz directly. The device plays it without upsampling. The
result is full-bandwidth audio with no resampling artifacts and no wasted
conversion work on either side.

**Why this priority**: This is the entire feature — removing the lossy 48→16→48
double-resample for the devices that suffer it. It directly improves audio
quality and removes the resample-mismatch failure class for native 48 kHz
satellites.

**Independent Test**: Connect a satellite that advertises 48 kHz downstream;
complete a voice turn; confirm the audio the device receives is 48 kHz PCM that
matches the gateway's source audio (full band preserved, no resampling stage on
the wire path), and is audibly equal-or-better than the 16 kHz path.

**Acceptance Scenarios**:

1. **Given** a satellite that advertises a 48 kHz downstream preference, **When**
   the gateway can produce 48 kHz, **Then** every downstream audio chunk is
   48 kHz PCM, explicitly labeled as such, and no 48→16 downsample occurs.
2. **Given** the same reply played to a 48 kHz device over the old 16 kHz path
   vs. the new 48 kHz path, **When** both are compared, **Then** the 48 kHz path
   preserves the full audio band (no high-frequency loss) and has no
   double-resample artifacts.
3. **Given** a 48 kHz negotiated session, **When** the device plays the audio,
   **Then** it does so without applying any sample-rate conversion of its own.

---

### User Story 2 - Existing 16 kHz devices are unaffected (Priority: P1)

A device that does not advertise a downstream rate (or advertises only 16 kHz) —
including every satellite built before this feature — continues to receive
16 kHz PCM exactly as today. No device-side change is required to keep working.

**Why this priority**: Backward compatibility is non-negotiable: the contract and
all existing satellites must keep working unchanged. A rate negotiation that
broke current 16 kHz devices would be unacceptable, so this is co-P1 with US1.

**Independent Test**: Connect a satellite that advertises nothing (or only
16 kHz); complete a voice turn; confirm it receives 16 kHz PCM, byte-for-byte
equivalent to today's behavior, with no errors.

**Acceptance Scenarios**:

1. **Given** a device that advertises no downstream rate, **When** a turn
   completes, **Then** it receives 16 kHz PCM (the unchanged default).
2. **Given** a device that advertises only 16 kHz, **When** a turn completes,
   **Then** it receives 16 kHz PCM.
3. **Given** a pre-existing satellite with no knowledge of this feature, **When**
   it connects to the upgraded gateway, **Then** it operates exactly as before
   with no reconfiguration.

---

### User Story 3 - Graceful fallback when a requested rate can't be served (Priority: P2)

A device advertises a downstream rate the gateway cannot produce (e.g. an
unsupported rate, or a future rate this gateway version doesn't know). The
gateway falls back to a rate it can produce (the 16 kHz default), labels every
chunk with the rate actually sent, and the session still works — no silence, no
crash, no garbled audio.

**Why this priority**: Robust negotiation must never strand a device. It's
essential for safe rollout across mixed gateway/device versions, but secondary
to delivering the core 48 kHz path (US1) and protecting existing devices (US2).

**Independent Test**: Have a device advertise an unsupported/unknown downstream
rate; confirm the gateway serves a supported fallback rate, every chunk is
labeled with the rate actually used, and the device plays intelligible audio.

**Acceptance Scenarios**:

1. **Given** a device advertising an unsupported downstream rate, **When** a turn
   completes, **Then** the gateway serves a supported fallback rate and labels
   each chunk with the rate actually sent.
2. **Given** a device advertising several rates best-first, **When** the gateway
   evaluates them, **Then** it serves the first one it can produce.
3. **Given** any negotiated outcome, **When** the device inspects a downstream
   chunk, **Then** the chunk unambiguously states the sample rate it carries
   (the device never has to assume).

---

### Edge Cases

- **Operator-configured default**: the gateway's configured default downstream
  format is honored when the client expresses no preference, the same way the
  existing downstream-codec default works.
- **Negotiation outcome is explicit per chunk**: the sample rate is stated on the
  downstream audio itself, so a device can adapt even if it didn't fully control
  the choice.
- **Mixed fleet / version skew**: an old gateway that doesn't understand a new
  rate preference ignores it and serves 16 kHz; a new gateway serving an old
  device serves 16 kHz. Neither side errors.
- **Compressed downstream codec (Opus) coexistence**: rate negotiation concerns
  the **raw PCM** downstream path; a compressed codec path that already carries
  its own rate handling is unaffected by, and not in scope of, this feature.
- **Upstream (device→gateway) audio is unchanged**: this feature is downstream
  only; mic audio continues exactly as today.
- **Quality direction**: negotiating a *higher* rate (48 kHz) must not degrade
  audio vs. 16 kHz; negotiating the existing rate must be byte-identical to today.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A native gRPC satellite MUST be able to advertise its preferred
  downstream PCM sample rate(s) to the gateway at session setup, best-first.
- **FR-002**: The gateway MUST honor the device's advertised downstream rate when
  it can produce that rate, sending downstream PCM at that rate.
- **FR-003**: When a device advertises 48 kHz and the gateway can produce it, the
  gateway MUST send 48 kHz PCM **without** downsampling to 16 kHz, and the device
  MUST be able to play it **without** upsampling — eliminating the 48→16→48
  double-resample.
- **FR-004**: Every downstream audio chunk MUST explicitly carry the sample rate
  it contains, so the device never assumes the rate.
- **FR-005**: When a device advertises no downstream rate preference, the gateway
  MUST send the existing default (16 kHz), preserving current behavior exactly.
- **FR-006**: When a device advertises a rate the gateway cannot produce, the
  gateway MUST fall back to a rate it can produce (default 16 kHz) and label the
  chunks with the rate actually sent — never silence, error, or mislabel.
- **FR-007**: The change MUST be backward-compatible and additive: existing
  satellites and the existing 16 kHz path keep working with no device-side
  change and no reconfiguration.
- **FR-008**: The negotiation MUST follow best-first preference order: among the
  device's advertised rates, the gateway serves the first it can produce.
- **FR-009**: An operator-configured default downstream format MUST be honored
  when the device expresses no preference (consistent with the existing
  downstream-codec default).
- **FR-010**: This feature MUST be limited to the downstream (gateway→device) PCM
  path; upstream (device→gateway) audio MUST be unchanged.
- **FR-011**: For a negotiated 48 kHz session, the audio the device receives MUST
  preserve the full audio band of the gateway's source (no high-frequency loss
  from a 16 kHz bottleneck).

### Key Entities *(include if feature involves data)*

- **Downstream rate preference**: the device's advertised, best-first list of
  desired downstream PCM sample rates, sent at session setup alongside the
  existing downstream-codec preference.
- **Downstream audio chunk**: a unit of gateway→device audio that explicitly
  states the codec/format **and sample rate** it carries.
- **Negotiated downstream format**: the (codec, sample-rate) the gateway selected
  for this session from the device's preferences and what the gateway can
  produce; the basis for whether resampling happens at all.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a 48 kHz-negotiated session, **zero** sample-rate conversions
  occur on the downstream path (none at the gateway, none at the device) — the
  gateway's 48 kHz audio reaches the speaker unresampled.
- **SC-002**: A 48 kHz-negotiated reply preserves the full audio band of the
  source (audio content above ~8 kHz is retained, where the 16 kHz path discards
  it), confirmed on at least one real reply.
- **SC-003**: A 48 kHz-negotiated reply is audibly equal-or-better than the same
  reply over the 16 kHz path, with no resampling artifacts, on a real device.
- **SC-004**: 100% of sessions where the device advertises no rate (or only
  16 kHz) receive 16 kHz PCM identical to pre-feature behavior.
- **SC-005**: 100% of sessions where the device advertises an unproducible rate
  receive a working, correctly-labeled fallback (no silence, no crash, no
  mislabeled audio).
- **SC-006**: Existing satellites require **no** code or config change to keep
  working after the gateway is upgraded.
- **SC-007**: Every downstream audio chunk's stated sample rate matches its actual
  payload rate in 100% of chunks across a test pass.

## Assumptions

- The gateway's internal voice pipeline is 48 kHz, so producing 48 kHz downstream
  is the **no-resample** path (the gateway passes its native audio through);
  16 kHz remains available as the downsampled default.
- The supported downstream PCM rates of interest are **16 kHz** (current default /
  legacy) and **48 kHz** (native, full-band). The negotiation mechanism is
  expressed generally (best-first preference) so additional rates could be added
  later, but only these two are required by this feature.
- Downstream rate is negotiated **alongside** the existing downstream-codec
  preference and selected with the same "best the gateway can produce, else
  default" policy, so the two compose rather than conflict.
- The satellite-facing wire contract is extended **additively**; no existing
  field changes meaning, so old clients/gateways interoperate (serving 16 kHz)
  without error.
- This complements feature 023 (which made the 16 kHz path produce *correct*
  audio): for 48 kHz-native devices, this feature removes that path's resampling
  entirely rather than merely making it correct.
- The C++ SDK / rpi-pipewire reference client already runs its audio boundary at
  48 kHz, so it is the primary beneficiary; whether/when each client adopts the
  48 kHz preference is a client-side decision out of scope here.

## Dependencies

- The existing gRPC downstream-codec negotiation (the device's best-first
  preference in the session header + the gateway's "first producible, else
  default" selection + the explicit per-chunk codec label) that this rate
  negotiation extends.
- The gateway's 48 kHz internal audio as the source for the no-resample 48 kHz
  downstream path.

## Out of Scope

- Upstream (device→gateway / microphone) sample-rate changes — downstream only.
- Compressed downstream codecs' internal rate handling (e.g. Opus); this feature
  is about the raw-PCM downstream rate.
- Changing the canonical 48 kHz internal pipeline rate.
- Client-side adoption decisions (which devices advertise 48 kHz, and when) and
  any device firmware work beyond the gateway contract.
- Arbitrary/continuous sample-rate support beyond the negotiated set required
  here (16 kHz and 48 kHz).
