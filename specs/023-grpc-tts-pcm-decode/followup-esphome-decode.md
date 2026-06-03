# Follow-up: esphome transport shares the same raw-bytes gap

**Status**: tracked, out of scope for feature 023.

## Observation

Feature 023 fixes the gRPC transport: `GrpcMediaAdapter.send_audio` now decodes
the provider-encoded TTS clip to canonical 48 kHz s16 mono PCM before queuing.

The **esphome** transport has the *same shape*: `EsphomeMediaAdapter.send_audio`
(`src/aivg_core/transports/esphome/media_adapter.py`) also does
`await self._out.put(pcm)` with the raw clip and then runs a 48 kHz→16 kHz
downsample over it — i.e. it would mis-handle a real (non-48 kHz-PCM) TTS clip the
same way gRPC did.

It has not surfaced as a bug because the esphome integration tests feed the echo
platform's non-audio sentinel bytes (and assert only that the payload is
non-empty), and esphome devices/providers in the field have happened to line up.

## Why out of scope here

The feature-023 request was explicitly scoped to the gRPC transport (the agent
building the gRPC client hit it). The fix is intentionally minimal and reuses the
neutral helper `aivg_core.audio.tts_decode.decode_tts_to_pcm48k`.

## Recommended follow-up

Apply the same one-line change to `EsphomeMediaAdapter.send_audio`: decode via
`decode_tts_to_pcm48k`, frame with `PcmFramer`, enqueue 48 kHz frames — identical
to the gRPC change. The shared helper already exists, so this is a small,
low-risk follow-up. Pair it with an esphome integration test that synthesizes a
real (non-48 kHz) container, mirroring `test_grpc_transport_basic.py`.

(Note: the esphome integration suite currently also has a **pre-existing,
unrelated** failure — `aioesphomeapi.api_pb2` has no `ConnectRequest` in the
installed version, a test-fixture/dep version mismatch in
`tests/fixtures/esphome_client.py` — which should be resolved independently.)
