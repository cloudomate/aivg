# Research: Negotiated downstream PCM sample rate (gRPC)

Feature `024-downstream-rate-negotiation`. All Technical-Context unknowns
resolved; no open `NEEDS CLARIFICATION`.

## Decision 1 — Represent the rate as a new `Codec` enum value, not a new `sample_rate` field

**Decision**: Add `CODEC_PCM_S16LE_48K = 3` to `aivg.satellite.v1.Codec` in
`proto/aivg/satellite/v1/audio.proto`. The device advertises it via the existing
`SessionHeader.downstream_codec_pref` (repeated `Codec`, best-first); the gateway
stamps it on the existing `AudioChunk.codec`. No new proto field.

**Rationale**:
- The contract **already encodes rate in the codec name** (`CODEC_PCM_S16LE_16K`).
  A 48 kHz sibling is the natural, consistent extension.
- It **reuses 100% of the negotiation + labeling machinery**: `downstream_codec_pref`
  (advertise, best-first), `select_downstream_codec` (first producible else
  default), and the explicit per-chunk `AudioChunk.codec` stamp. Zero new wire
  surface to negotiate or validate.
- It is **purely additive**: a new enum value. Old clients never send it; old
  gateways/SDKs map the unknown value to `CODEC_UNSPECIFIED` (proto3 open enum
  semantics + the C++ `from_proto_codec` default), so nothing breaks.

**Alternatives considered**:
- **A dedicated `sample_rate` field** on `SessionHeader` + `AudioChunk` (codec ×
  rate as independent axes). More general (any rate, any codec), but adds a second
  negotiation/labeling surface, a codec×rate validity matrix, and a parallel
  fallback path — for a feature that needs exactly {16 k, 48 k} PCM. Rejected:
  disproportionate surface for the requirement; the enum reuses everything.
- **A free-form rate in `attrs`/metadata**: rejected — unvalidated, not first-class,
  no clean per-chunk labeling.

## Decision 2 — Gateway honors 48 kHz by *skipping* the downsample (passthrough), not by upsampling

**Decision**: In `GrpcMediaAdapter.run_outbound_pump`, make the 48 kHz→16 kHz
`audioop.ratecv` downsample **conditional**: when the negotiated codec is
`CODEC_PCM_S16LE_48K`, pass the session's native 48 kHz PCM straight to the
payload (no resample); otherwise downsample 48→16 as today.

**Rationale**: `Session` feeds the adapter **native 48 kHz** PCM (feature 023
made `_out` truly 48 kHz). So 48 kHz downstream is literally "do nothing" — the
cleanest possible path and the whole point (SC-001: zero resamples). It also
makes the 16 kHz path bit-identical to today (the conditional only adds a branch).

**Alternatives considered**: keep downsampling and add a separate 48 kHz encoder
path — rejected, there is no encoding to do for PCM passthrough; the native audio
*is* the payload.

## Decision 3 — 48 kHz PCM is always "producible"; selection + fallback reuse the codec policy

**Decision**: In `codec.py`, mark `CODEC_PCM_S16LE_48K` producible (the gateway's
pipeline is native 48 kHz, so it can always emit 48 kHz PCM), add it to the
name→codec map (`"pcm48k"`) for the operator default, and make `encode()` a
passthrough for it. `select_downstream_codec` then needs **no structural change**:
best-first over the client prefs, first producible wins, else the configured
default, else `CODEC_PCM_S16LE_16K`.

**Rationale**: FR-002/008 (honor best-first producible) and FR-006 (fallback to a
producible rate, default 16 kHz) fall out of the existing selection for free.
Unknown/unproducible prefs are simply skipped → 16 kHz default, with the actual
codec stamped per chunk (FR-004/006). No new fallback code.

## Decision 4 — Bump the contract version 0.3.0 → 0.4.0 (additive minor)

**Decision**: Bump `CONTRACT_VERSION` in `src/aivg_cli/cli.py` from `"0.3.0"` to
`"0.4.0"` and update the three assertions (`tests/unit/test_cli_help_contract.py`,
`tests/unit/test_cli_tagline.py`, `tests/integration/test_install_from_built_wheel.py`).

**Rationale**: Adding a wire-visible `Codec` value is an additive contract change,
and the project's established convention is to bump the **contract** minor for
additive wire changes (feature 021 bumped `0.2.0→0.3.0`; the esphome contract
bumped `1.0.0→1.1.0`). This is **independent of the PyPI package version** (which
is at `0.3.1`); contract version tracks the wire schema, package version tracks
the release.

**Alternatives considered**: leave the contract at 0.3.0 (an open-enum addition is
technically backward-compatible). Rejected: the convention is to surface additive
wire capability via the contract minor, and the negotiation smoke / SDKs key off
it. (If the maintainer prefers no contract bump, this is the one reversible knob —
flagged for confirmation.)

## Decision 5 — Scope: gateway + contract now; client adoption is the consuming follow-on

**Decision**: Deliver the contract + gateway honoring, validated with a Python
gRPC **test client** that advertises 48 kHz and asserts full-band 48 kHz chunks.
Do **not** modify the C++ SDK / rpi-pipewire in this feature.

**Rationale**: The spec explicitly out-scopes "which devices advertise 48 kHz, and
when." The additive enum means old C++ stubs keep compiling (unknown value →
`Unspecified`), so nothing is forced. The user-visible device benefit lands when a
client adopts the 48 kHz preference; that consuming change (C++ `Codec` mapping +
`downstream_pref = 48k` + native playback, and the rpi-pipewire example) is a
small, separate follow-on — and the natural vehicle for the Principle V live gate
on the XVF3800 (48 kHz-native) rig.

**Note / dependency**: there is an in-flight C++ branch
(`fix/cpp-grpc-48k-resample`) that made the SDK's audio boundary uniformly 48 kHz
with internal 16↔48 resampling; on `main` today the C++ gRPC transport delivers
the raw downstream payload to the app without resampling. The 48 kHz adoption
should be reconciled with that branch so the device skips (rather than adds) a
resample.

## Resolved Technical Context

| Item | Resolution |
|------|------------|
| Wire shape | new `Codec` value `CODEC_PCM_S16LE_48K = 3` (additive) |
| Negotiation | existing `downstream_codec_pref` best-first + `select_downstream_codec` |
| Gateway behavior | pump skips 48→16 downsample for 48 kHz codec (passthrough) |
| Producibility / fallback | 48 kHz always producible; unproducible prefs → 16 kHz default, stamped |
| Contract version | 0.3.0 → 0.4.0 (additive minor); package version unchanged (0.3.1) |
| Stub regen | Python via `scripts/gen_proto.sh`; C++ stubs untouched (deferred to adoption) |
| Test strategy | unit (select/pump) + contract (enum) + integration (48k turn) + live gate |
