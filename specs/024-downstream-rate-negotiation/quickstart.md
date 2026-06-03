# Quickstart: Negotiated downstream PCM sample rate (gRPC)

How to build, test, and **prove** that a 48 kHz satellite gets resample-free
full-band downstream audio.

## What changed (one sentence)

A new additive `Codec` value `CODEC_PCM_S16LE_48K` lets a device advertise 48 kHz
downstream PCM; the gateway then passes its native 48 kHz audio straight through
(no 48→16 downsample), removing the lossy 48→16→48 double-resample.

## Apply the contract change

```bash
# 1. Edit proto/aivg/satellite/v1/audio.proto: add CODEC_PCM_S16LE_48K = 3
# 2. Regenerate the Python stubs (checked in):
bash scripts/gen_proto.sh
# 3. Confirm the enum value exists:
./.venv/bin/python -c "from aivg_core.transports.grpc._generated import audio_pb2 as a; print(a.Codec.Value('CODEC_PCM_S16LE_48K'))"
```

## Run the tests

```bash
./.venv/bin/python -m pytest \
  tests/contract/test_grpc_contract.py \
  tests/unit/test_grpc_codec.py \
  tests/unit/test_grpc_media_adapter.py \
  tests/integration/test_grpc_transport_basic.py -q

# contract-version bump (0.3.0 -> 0.4.0):
./.venv/bin/python -m pytest \
  tests/unit/test_cli_help_contract.py tests/unit/test_cli_tagline.py -q
./.venv/bin/python -m pytest tests/integration/test_grpc_backpressure.py -q  # bounds preserved
```

### Expectations

- A session advertising `[CODEC_PCM_S16LE_48K]` → every `AudioChunk` is stamped
  `CODEC_PCM_S16LE_48K`, payload is 48 kHz s16 mono (1920 B / 20 ms frames), and
  the decoded audio reconstructs the source **with its full band** (content above
  ~8 kHz preserved — the regression-of-improvement guard).
- A session advertising nothing or `[CODEC_PCM_S16LE_16K]` → `AudioChunk`s are
  `CODEC_PCM_S16LE_16K`, **byte-identical to today**.
- A session advertising an unproducible codec → falls back to 16 kHz, stamped
  correctly. No error/silence.
- `aivg --contract-version` reports `0.4.0`.

## Quick manual check (no hardware)

Drive a turn over a real `grpc.aio` channel advertising 48 kHz, capture
`AudioChunk`s, and verify payload length implies 48 kHz (≈ 3× the 16 kHz byte
count for the same clip) and that the codec stamp is `CODEC_PCM_S16LE_48K`.
(Reuse the harness shape from `specs/023-grpc-tts-pcm-decode/live_proof.py`,
setting `downstream_codec_pref=[CODEC_PCM_S16LE_48K]` and removing the gateway
downsample assertion.)

## Live end-to-end gate (Principle V — REQUIRED before "done")

The motivating constraint is the **XVF3800 (48 kHz-native, I2S 48 kHz firmware)**.
Prove the no-resample path on real 48 kHz hardware (`iva` — RPi5 + XVF3800):

1. Run the gateway gRPC audio plane with a real (non-48 kHz) TTS provider.
2. Connect a client that advertises `[CODEC_PCM_S16LE_48K]` (the gRPC test client,
   or the C++ SDK once it adopts the 48 kHz pref).
3. **Confirm**: every `AudioChunk` is stamped 48 kHz; the gateway performs **no**
   48→16 downsample and the device performs **no** 16→48 upsample (zero resamples,
   SC-001); playback is clean and **full-band** (SC-002/003).
4. **A/B**: the same reply over 16 kHz vs 48 kHz — 48 kHz retains high-frequency
   content the 16 kHz path discards, with no resampling artifacts.
5. **Back-compat**: a client advertising nothing still plays 16 kHz fine (SC-004).

(See `specs/023-grpc-tts-pcm-decode/live_proof.py` and the `iva` rig notes for the
capture-and-play harness; bump the client's `downstream_codec_pref` to 48 kHz and
play the captured 48 kHz WAV directly.)

## Rollback

Additive and isolated: revert the proto enum value (regenerate), the `codec.py`
producibility/encode entries, the `media_adapter.py` conditional, and the
`CONTRACT_VERSION` bump. No data/state migration. Old 16 kHz behavior is the
fallback throughout, so even a partial rollback degrades safely to 16 kHz.
