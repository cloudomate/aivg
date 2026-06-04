# Quickstart: Opus upstream (mic → STT) voice

How to build, test, and prove that a satellite's Opus mic uplink is transcribed
correctly at a fraction of the bandwidth.

## What changed (one sentence)

A new additive `ClientFrame.opus` arm lets a gRPC satellite send Opus-encoded
48 kHz mic audio; the gateway decodes it to 48 kHz and feeds STT exactly like the
raw-PCM path (which already runs STT at 48 kHz) — at ~10× less uplink bandwidth.

## Apply the contract change

```bash
# 1. Edit proto/aivg/satellite/v1/audio.proto: add OpusChunk + ClientFrame.opus=4
#    + SessionHeader.upstream_codec_pref=3
# 2. Regenerate Python stubs:
bash scripts/gen_proto.sh
# 3. Regenerate C++ stubs (in the rpi-builder container or with protoc).
# 4. Confirm:
./.venv/bin/python -c "from aivg_core.transports.grpc._generated import audio_pb2 as a; print(a.ClientFrame.DESCRIPTOR.fields_by_name['opus'].number)"   # 4
```

## Run the tests

```bash
# Gateway (Python):
./.venv/bin/python -m pytest \
  tests/contract/test_grpc_contract.py \
  tests/unit/test_grpc_media_adapter.py \
  tests/integration/test_grpc_transport_basic.py -q
# contract-version bump 0.3.0 -> 0.4.0:
./.venv/bin/python -m pytest tests/unit/test_cli_help_contract.py tests/unit/test_cli_tagline.py -q

# C++ SDK (rpi-builder container — gRPC needs grpc++):
docker exec rpi-builder bash -lc 'cd /workspace/sdks/cpp && \
  cmake -B build-docker -DAIVG_SAT_ENABLE_GRPC=ON -DAIVG_SAT_BUILD_TESTS=ON && \
  cmake --build build-docker -j4 && (cd build-docker && ctest --output-on-failure)'
```

### Expectations

- **Gateway**: an `opus` `ClientFrame` is decoded to 48 kHz and an utterance is
  transcribed to text **equivalent to the raw-PCM path** (use a fixed test clip
  through the echo platform's `transcribe`, which echoes byte/length info — assert
  the decoded audio reaches STT, and a real-STT variant matches the PCM transcript).
- A **malformed** `opus` packet is dropped; the session/turn survives (FR-007).
- The **`pcm` path is byte-for-byte unchanged** (regression guard).
- **C++**: with the gateway advertising acceptance + `grpc_upstream_opus=true`,
  the inproc test sees the client send `opus` arms and `mic_frame_samples()==960`;
  without acceptance it sends `pcm` (`==320`).
- `aivg --contract-version` reports `0.4.0`.
- **Bandwidth (SC-002)**: the Opus arms for a fixed utterance total ≥ ~5× fewer
  bytes than the equivalent raw 16 kHz PCM.

## Live end-to-end gate (Principle V — REQUIRED before "done")

On `iva` (RPi5 + XVF3800), prove the on-device Opus encode → gateway decode → STT
loop:

1. Run the gateway with the gRPC audio plane + a real STT provider, advertising
   upstream-Opus acceptance.
2. Run the C++ satellite on `iva` with `grpc_upstream_opus=true` (captures 48 kHz,
   encodes Opus upstream).
3. **Confirm**: speak a known phrase → the gateway transcribes it **correctly**
   (equivalent to the raw-PCM path); the device encodes (no crash, real-time);
   the mic uplink bytes are materially smaller than raw PCM (capture a count).
4. **Fallback**: point the same device at a gateway that does NOT advertise
   acceptance → it streams raw PCM and still transcribes (SC-004).
5. **Endpointing**: wake / end-of-utterance / barge-in behave identically (SC-007).

(Reuse the `iva` rig + the `live_proof.py` harness shape; add an Opus-encode mic
source and assert the returned transcript.)

## Rollback

Additive and isolated: revert the proto arm (regen), the gateway
`push_inbound_opus` dispatch, the register acceptance signal, the C++ upstream
mode, and the `CONTRACT_VERSION` bump. Raw-PCM upstream is the fallback
throughout, so partial rollback degrades safely to PCM.
