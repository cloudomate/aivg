# Contract: `CODEC_PCM_S16LE_48K` downstream rate negotiation

**Contract**: `aivg.satellite.v1` (audio plane) · **Change**: additive ·
**Version**: 0.3.0 → **0.4.0**

This is a wire-contract change consumed by every satellite SDK. It is **additive**
— no existing field changes meaning — so old↔new interoperate (at 16 kHz).

## Proto delta (`proto/aivg/satellite/v1/audio.proto`)

```diff
 enum Codec {
   CODEC_UNSPECIFIED   = 0;
   CODEC_OPUS          = 1;
   CODEC_PCM_S16LE_16K = 2;
+  CODEC_PCM_S16LE_48K = 3;  // raw int16 LE mono PCM @ 48 kHz (device-native, no resample)
 }
```

Nothing else in the proto changes. `SessionHeader.downstream_codec_pref` and
`AudioChunk.codec` already carry this value by type.

After editing the proto: regenerate the **Python** stubs with
`scripts/gen_proto.sh` (checked-in `src/aivg_core/transports/grpc/_generated/`).
C++ stubs are intentionally **not** regenerated here (client adoption is a
follow-on; old C++ stubs keep compiling).

## Negotiation semantics (unchanged mechanism, extended values)

1. **Advertise** (device → gateway, in the `Audio.Stream` `SessionHeader`):
   `downstream_codec_pref` is a best-first list. A 48 kHz-native device sends
   `[CODEC_PCM_S16LE_48K, CODEC_PCM_S16LE_16K]` (48 k preferred, 16 k acceptable).
2. **Select** (gateway): first preferred codec it can **produce**; else the
   configured default; else `CODEC_PCM_S16LE_16K`. `CODEC_PCM_S16LE_48K` is always
   producible (pipeline is native 48 kHz).
3. **Label** (gateway → device, every `AudioChunk`): `codec` states the actual
   format. For `CODEC_PCM_S16LE_48K`, `payload` is 48 kHz s16 mono PCM
   (1920 B / 20 ms); for `CODEC_PCM_S16LE_16K`, 16 kHz (640 B / 20 ms).

## Behavioral contract (gateway)

| Client `downstream_codec_pref` | Gateway selects | Downstream payload | Resample |
|--------------------------------|-----------------|--------------------|----------|
| `[…48K, 16K]`, gateway native 48 k | `48K` | 48 kHz PCM | **none** |
| `[]` (empty) | configured default → `16K` | 16 kHz PCM | 48→16 (as today) |
| `[16K]` | `16K` | 16 kHz PCM | 48→16 (as today) |
| `[<unknown/unproducible>]` | default → `16K` | 16 kHz PCM | 48→16 (as today) |
| `[OPUS, …]`, no encoder | skip OPUS → next producible | per next | per codec |

## Compatibility matrix

| | New gateway (knows 48K) | Old gateway (0.3.0) |
|---|---|---|
| **New client** (advertises 48K) | 48 kHz, no resample ✅ | 48K ignored (unknown) → 16 kHz ✅ |
| **Old client** (16K only) | 16 kHz (unchanged) ✅ | 16 kHz (unchanged) ✅ |

No combination errors; the worst case is the existing 16 kHz path.

## Test obligations

- **Contract**: `CODEC_PCM_S16LE_48K` exists in the generated enum
  (`tests/contract/test_grpc_contract.py`).
- **Selection**: 48 k chosen when preferred+producible; unproducible pref → 16 k
  default; empty → default (`tests/unit/test_grpc_codec.py`).
- **Pump**: 48 k negotiated ⇒ no downsample, payload is 48 kHz / 1920 B-framed and
  reconstructs the source full-band; 16 k negotiated ⇒ byte-identical to today
  (`tests/unit/test_grpc_media_adapter.py`).
- **Integration**: a turn advertising `[48K]` yields `AudioChunk`s stamped `48K`
  with 48 kHz payload; a turn advertising nothing yields `16K`
  (`tests/integration/test_grpc_transport_basic.py`).
- **Version**: `aivg --contract-version` reports `0.4.0` (3 assertions updated).

## Non-goals

- No `sample_rate` field (rate stays encoded in the codec value — Decision 1).
- No upstream/mic rate change. No Opus rate change. No C++ SDK change here.
