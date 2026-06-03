# PIVOT: solve via Opus, not a new PCM-48k codec

**Date**: 2026-06-03 · **Decision by**: maintainer · **Status**: implemented

## What changed

The original spec/plan/research/tasks in this directory describe adding a new
`CODEC_PCM_S16LE_48K` wire codec so a device could negotiate **raw 48 kHz PCM**
downstream. During implementation the maintainer asked: *Opus already handles
variable sample rate — why add a PCM codec?*

That's correct, and the implementation pivoted to **Opus**:

- Opus is **internally always 48 kHz**; the decoder outputs whatever rate it is
  configured for. The bug was that the gateway **encoded downstream Opus at
  16 kHz** (after a 48→16 downsample), band-limiting to 8 kHz.
- The fix: **encode downstream Opus at native 48 kHz** (skip the downsample). A
  device that decodes Opus at 48 kHz (the C++ `OpusBridge` already does) gets
  the **full band**; a 16 kHz-decoder device decodes the same packets to 16 kHz.

## Why this is better than the PCM-48k codec

| | Opus-48k (chosen) | PCM-48k codec (original) |
|---|---|---|
| Wire/proto/contract change | **none** (`CODEC_OPUS` exists) | new enum value + contract 0.3.0→0.4.0 |
| New dependency | **none** (PyAV's bundled libopus) | none |
| Bandwidth | compressed (~7× smaller) | raw (3× the 16 kHz bytes) |
| Quality | lossy but full-band | lossless full-band |
| CPU | encode/decode (cheap on RPi) | zero |
| Client change to benefit | advertise `[OPUS]` (already supported) | advertise the new codec |

For a voice gateway, Opus is the right downstream codec; the PCM-48k path was a
heavier way to reach the same full-band outcome with a contract change.

## Implementation (what actually landed)

Gateway-only, no contract change (contract stays **0.3.0**):

- `src/aivg_core/transports/grpc/codec.py`
  - `_opus_available()` now checks **PyAV's libopus** (PyAV is already a hard
    dep) → Opus is effectively always producible (no `opuslib`/system libopus).
  - new stateful `OpusEncoder48k` (PyAV `CodecContext`, 48 kHz s16 mono).
  - `encode()` is now PCM-passthrough only (Opus goes through `OpusEncoder48k`).
- `src/aivg_core/transports/grpc/media_adapter.py`
  - `__init__` builds an `OpusEncoder48k` when `CODEC_OPUS` is negotiated.
  - `run_outbound_pump` encodes Opus **directly from native 48 kHz** (no
    downsample) and flushes the encoder tail at stream end; the raw-PCM path
    still downsamples 48→16 (unchanged).
- Tests: `tests/unit/test_grpc_codec.py` (Opus now producible; `OpusEncoder48k`
  round-trips a 12 kHz tone full-band), `tests/unit/test_grpc_media_adapter.py`
  (Opus downstream is 48 kHz full-band + compressed), `tests/integration/
  test_grpc_transport_basic.py` (a turn advertising `[OPUS]` → 48 kHz Opus chunks
  that decode full-band). `tests/_audio_fixtures.py` gains `opus_decode_48k`.

## Behavior change to note

Before, Opus downstream wasn't producible (no `opuslib`), so a client advertising
Opus silently got 16 kHz PCM. Now Opus **is** producible (via PyAV), so a client
advertising `[OPUS, …]` gets full-band 48 kHz Opus. Clients that advertise only
PCM (the C++ SDK default, browsers, esphome) are unaffected — still 16 kHz PCM.

## C++ SDK / rpi-pipewire adoption (DONE — included in this feature)

The gRPC client now advertises Opus best-first with a 16 kHz PCM fallback, and
decodes Opus to native 48 kHz for playback (the `OpusBridge` already decodes at
48 kHz). Changes under `sdks/cpp/`:

- `src/transport/grpc_transport.hpp` — `GrpcTransportOptions.downstream_pref`
  default → `Codec::Opus`.
- `src/transport/grpc_transport.cpp` — `begin()` advertises
  `[downstream_pref, CODEC_PCM_S16LE_16K]` (best-first + guaranteed fallback).
- `include/aivg/sat/satellite.hpp` — new public `bool grpc_downstream_opus = true`
  (set false to force 16 kHz PCM downstream; no effect on WebRTC).
- `src/satellite.cpp` — wires the option into `GrpcTransportOptions`.
- `tests/grpc_transport_inproc_test.cpp` — asserts the client advertises
  `[Opus, PCM_16K]`. Full C++ ctest (6) green in the rpi-builder container.
- `README.md` — documents the 48 kHz Opus downstream + the opt-out.

The **rpi-pipewire example already runs at 48 kHz** (`kRate = 48000`), so the
Opus-default downstream (48 kHz) matches its playback — with the old 16 kHz PCM
downstream it would have played ~3× too fast. No example code change needed.

> Upstream mic on the gRPC tier is still 16 kHz (`mic_frame_samples()==320`);
> making the *capture* boundary uniformly 48 kHz is the separate
> `fix/cpp-grpc-48k-resample` work, out of scope here (downstream only).

## Still open

- **Live gate (Principle V)**: prove full-band Opus end-to-end on `iva`
  (RPi5 + XVF3800).
- The original PCM-48k spec/plan/research/tasks in this dir are **superseded** by
  this note (kept for history).
