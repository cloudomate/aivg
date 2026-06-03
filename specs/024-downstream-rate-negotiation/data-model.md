# Data Model: Negotiated downstream PCM sample rate (gRPC)

No persisted entities. The "data" is the wire contract delta and the in-flight
audio-format invariants. All changes are **additive** to existing messages.

## Wire contract delta (additive)

### `Codec` enum — one new value
```
enum Codec {
  CODEC_UNSPECIFIED   = 0;
  CODEC_OPUS          = 1;
  CODEC_PCM_S16LE_16K = 2;
  CODEC_PCM_S16LE_48K = 3;   // NEW — raw int16 LE mono PCM @ 48 kHz (native, no resample)
}
```
- **Backward compatibility**: proto3 open enum. Old senders never emit `3`; old
  receivers surface an unknown `3` as their default (`CODEC_UNSPECIFIED` /
  C++ `Codec::Unspecified`). Nothing breaks.

### Reused fields (NO change)
- `SessionHeader.downstream_codec_pref` (`repeated Codec`, best-first) — the device
  now MAY include `CODEC_PCM_S16LE_48K` in its preference list.
- `AudioChunk.codec` (`Codec`, explicit per chunk) — the gateway stamps the codec
  it actually produced, now possibly `CODEC_PCM_S16LE_48K`.
- `PcmChunk` (upstream mic) — unchanged (still 16 kHz; this feature is downstream
  only, FR-010).

## Audio-format invariants (per negotiated session)

| Negotiated codec | Gateway pump | Wire payload | Resamples on path |
|------------------|--------------|--------------|-------------------|
| `CODEC_PCM_S16LE_16K` (default/legacy) | 48→16 downsample (as today) | 16 kHz s16 mono, 640 B/20 ms | gateway 48→16 (+ device 16→48 if 48 k device) |
| `CODEC_PCM_S16LE_48K` (NEW) | **passthrough** (no resample) | 48 kHz s16 mono, 1920 B/20 ms | **none** |
| `CODEC_OPUS` (if encoder present) | unchanged | Opus | (Opus-internal; out of scope) |

**Invariant (FR-004/SC-007)**: `AudioChunk.codec` ALWAYS matches the payload's
actual rate/format — the device never assumes.

## Entities (conceptual)

- **Downstream rate preference** — the device's best-first list in
  `SessionHeader.downstream_codec_pref`; MAY contain `CODEC_PCM_S16LE_48K`.
- **Negotiated downstream codec** — `select_downstream_codec(prefs, default)`:
  first client-preferred codec the gateway can produce, else the configured
  default, else `CODEC_PCM_S16LE_16K`. `CODEC_PCM_S16LE_48K` is **always
  producible** (pipeline is native 48 kHz).
- **Downstream audio chunk** — `AudioChunk{codec, payload, seq}`; `codec` labels
  the rate/format of `payload`.

## Selection / state rules

- **Best-first producible** (FR-002/008): scan `downstream_codec_pref`; first
  producible wins. `CODEC_PCM_S16LE_48K` and `CODEC_PCM_S16LE_16K` always
  producible; `CODEC_OPUS` producible iff an encoder is importable.
- **Default** (FR-005/009): empty prefs → operator-configured default
  (`transports.grpc.downstream_codec`, extended to accept `"pcm48k"`) → else
  `CODEC_PCM_S16LE_16K`.
- **Fallback** (FR-006): an unproducible/unknown pref is skipped, never errors;
  the chunk is stamped with whatever was actually selected.
- **Per-session, fixed for the session**: the codec is chosen once from the
  `SessionHeader` and used for every `AudioChunk` of that stream (as today).

## Components touched

- `codec.py` — add the `CODEC_PCM_S16LE_48K` alias; `producible()` true;
  `encode()` passthrough; name map `"pcm48k"`.
- `media_adapter.py` — `run_outbound_pump` conditional downsample (passthrough at
  48 kHz). `__init__` may precompute a `self._downstream_sr` from the codec for the
  payload-rate/label.
- `audio.proto` (+ regenerated Python stubs) — the enum value.
- `cli.py` — `CONTRACT_VERSION` 0.3.0 → 0.4.0.
