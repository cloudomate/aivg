# Research: Opus upstream (mic → STT) voice

Feature `025-upstream-opus-stt`. Technical-Context unknowns resolved; the 2026-06-04
clarifications fixed the wire/encode/capture-rate decisions, and code inspection
resolved the handshake + STT-rate points below.

## Decision 1 — Additive Opus mic arm on `ClientFrame` (self-describing)

**Decision**: Add `OpusChunk opus = 4` to the `ClientFrame` oneof in
`proto/aivg/satellite/v1/audio.proto` (an `OpusChunk{ bytes payload; uint64 ts_ns }`
mirroring `PcmChunk`), plus `repeated Codec upstream_codec_pref` on `SessionHeader`
(symmetric to `downstream_codec_pref`). Regenerate Python + C++ bindings.

**Rationale**: The arm is **self-describing** — the gateway dispatches on
`WhichOneof("body")` (`pcm` vs `opus`) and never has to guess the upstream codec.
`upstream_codec_pref` lets the device declare intent and the gateway log/confirm
it. Purely additive: old gateways see field 4 as an unknown field and the oneof as
"not set", so they ignore Opus frames (which is exactly why Decision 4's handshake
is needed). Reuses the existing `Codec` enum (`CODEC_OPUS`).

**Alternatives**: a codec tag on a single audio arm (rejected — the existing
`PcmChunk` arm is rate-baked and untagged; a separate `opus` arm is cleaner and
matches the downstream `AudioChunk{codec,payload}` asymmetry already in the
contract). A top-level `upstream_codec` only on SessionHeader with PCM-or-Opus in
the same `pcm` arm (rejected — overloads `PcmChunk`, not self-describing).

## Decision 2 — Gateway decodes Opus → 48 kHz → feeds the Session directly (no 16 kHz step)

**Decision**: A new `GrpcMediaAdapter.push_inbound_opus(payload)` decodes the Opus
packet to **48 kHz** s16 mono (stateful PyAV libopus decoder, mirroring the 024
encoder), reframes to 20 ms (1920 B), and enqueues onto the same `_in` queue the
raw-PCM path feeds. The `stream_handler` dispatches the `opus` arm to it; the
`pcm` arm path is unchanged.

**Rationale — refines the clarification**: the clarification said "decode → 48 kHz
→ resample to 16 kHz → STT". Code inspection shows the gateway actually feeds STT
at **48 kHz** (`session.py`: `transcribe(b"".join(utterance), sample_rate=48000)`;
the existing raw-PCM path upsamples 16→48 in `push_inbound` *before* the Session).
So decoding Opus to 48 kHz and joining the existing 48 kHz pipeline is the faithful,
simpler realization — the redundant 48→16→48 round trip is omitted. STT receives
the same 48 kHz audio it gets from the PCM path, so transcripts are equivalent
(FR-002/003). **Flagged for confirmation** since it departs from the literal
clarification wording (but matches its intent and the actual STT rate).

**Alternatives**: decode → 48 → downsample → 16 → feed STT at 16 kHz (rejected —
inconsistent with the PCM path which gives STT 48 kHz, and adds redundant work;
Whisper-class STT downsamples internally regardless).

## Decision 3 — Capture rate is negotiation-dependent; no on-device resampler (Option C)

**Decision**: The C++ gRPC transport's `mic_frame_samples()` returns **960** when
Opus upstream is in effect and **320** on PCM fallback; `send_mic` either
Opus-encodes the 48 kHz frame (`OpusBridge::encode`, 960 samples → one packet) and
sends the `opus` arm, or wraps the 16 kHz frame in the `pcm` arm. **No `mic_down`
resampler** in either case (per the Q1=C clarification).

**Rationale**: The device captures at the rate matching the agreed codec, so no
on-device resampling is ever needed — the cleanest device path. `OpusBridge`
already encodes 48 kHz mono at 960 samples/frame (used by WebRTC today), so the
encode path exists. The app's `audio_input` callback is asked for the negotiated
frame size; for a 48 kHz-native rig (rpi-pipewire, `kRate=48000`) this is natural.

**Consequence**: the mic capture rate is fixed per session and known before the
mic pump starts — which requires Decision 4 (the device must learn acceptance
before `beginSession`).

## Decision 4 — Acceptance handshake rides the register/capability plane (before the voice stream)

**Decision**: The gateway advertises **upstream-Opus acceptance** in the
**register/adoption reply** the device already consumes for `chosen_transport`
(C++ control plane parses it during `connect()`, before `beginSession()` opens the
Audio.Stream). The device sets its upstream mode (and thus capture rate) from that
signal; if absent (old gateway), it uses raw PCM. Concretely: add an
`upstream_opus` (or `audio_capabilities`) field to the register reply
(WS JSON for the C++ control plane; `RegisterReply` for the gRPC Management
service) — additive.

**Rationale**: Option C needs the device to choose its capture rate *before*
streaming; the only signal available that early is the register/capability
exchange (Principle III capability negotiation, where `chosen_transport` already
lives). The voice-stream arm is self-describing, so the gateway side needs no
extra negotiation — the handshake exists purely so the device doesn't send Opus to
a gateway that would drop it (FR-006 safe fallback).

**Alternatives**:
- *SessionHeader-only* (advertise `upstream_codec_pref`, gateway acks on the
  stream): rejected — the ack arrives after the device already committed to a
  capture rate (chicken-and-egg with Option C).
- *Gate on gateway contract_version ≥ 0.4.0*: viable and lighter, but the device
  doesn't reliably receive the gateway's contract version today; an explicit
  capability bit is clearer and self-documents. (Kept as a fallback if the
  register-reply change proves heavy.)

## Decision 5 — Contract bump 0.3.0 → 0.4.0 (additive)

**Decision**: Adding the `opus` `ClientFrame` arm (and `upstream_codec_pref`, and
the register capability) is an additive wire change → bump `CONTRACT_VERSION`
`0.3.0` → `0.4.0` and update the three assertions (as the reverted 024 PCM path
would have). Package version is bumped separately at release.

**Rationale**: Unlike 024 (which reused the existing `CODEC_OPUS` with no schema
change), this adds new wire fields, so the additive-minor bump is warranted, per
the project convention (021 did 0.2.0→0.3.0 for additive).

## Decision 6 — Reuse existing Opus engines; enable on-device gRPC encode (reverses 022 R-3)

**Decision**: Gateway decode uses **PyAV's libopus** (already a dep, used by 024);
device encode uses the C++ **`OpusBridge`** (already present, used by WebRTC). This
**enables on-device Opus encode on the gRPC path**, which feature 022 R-3 deferred.

**Rationale**: R-3 deferred encode for the ESP32/MVP constraint; the gRPC tier is
RPi-class (POSIX, ample CPU) and ESP32 stays on WebRTC, so the constraint is not
violated. No new dependency on either side. Per Principle V, prove on real
hardware (live gate).

## Resolved Technical Context

| Item | Resolution |
|------|------------|
| Wire shape | additive `OpusChunk opus = 4` on `ClientFrame` + `SessionHeader.upstream_codec_pref` |
| Gateway path | decode Opus → 48 kHz → existing `_in`/Session (STT at 48 kHz; no 16 kHz step) |
| Capture rate | negotiation-dependent: 960 (Opus) / 320 (PCM); no on-device resampler |
| Handshake | gateway advertises upstream-Opus acceptance in the register reply (pre-voice) |
| Engines | gateway PyAV libopus decode; device `OpusBridge` encode (both already present) |
| Contract version | 0.3.0 → 0.4.0 (additive) |
| Regen | Python via `scripts/gen_proto.sh`; C++ stubs regenerated from the proto |
| Out of scope | WebRTC upstream (already Opus); esphome upstream |
