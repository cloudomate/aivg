# Contracts: C++ SDK gRPC Transport (feature 022)

This feature introduces **no new wire contract**. It is a new *consumer* of
feature 021's canonical schema and adds one *internal* C++ abstraction.

## 1. Consumed wire contract (feature 021 — unchanged)

`proto/aivg/satellite/v1/audio.proto` (and `management.proto` for Phase 2) — the
single source of truth, already shipped. The C++ SDK generates client stubs from
it; the gateway generates server stubs from the same file, so the wire cannot
drift (FR-001).

- Voice plane: `Audio.Stream(stream ClientFrame) → (stream ServerFrame)`.
- Upstream `ClientFrame`: `SessionHeader` (first), `PcmChunk` (raw 16 kHz s16le,
  20 ms / 640 B), `ClientEvent` (wake / end-of-utterance / barge-in).
- Downstream `ServerFrame`: `AudioChunk` (explicit `Codec`), `ServerEvent`
  (speaking/vad), `Transcript` (partial/final).
- Negotiation: `RegisterRequest.transport_capabilities`,
  `RegisterReply.chosen_transport`.

### Codegen (C++)

`cmake/GenerateProto.cmake` runs (POSIX tier, when `protoc` is present):

```sh
protoc -I <repo>/proto \
  --cpp_out=sdks/cpp/src/grpc/_generated \
  --grpc_out=sdks/cpp/src/grpc/_generated \
  --plugin=protoc-gen-grpc=$(which grpc_cpp_plugin) \
  aivg/satellite/v1/audio.proto
```

Generated `audio.pb.{h,cc}` + `audio.grpc.pb.{h,cc}` are **checked into
`src/grpc/_generated/`** so a consumer build needs no protoc (mirrors feature
021's checked-in Python stubs). The whole gRPC path is gated by
`AIVG_SAT_ENABLE_GRPC` inside the POSIX branch only — the ESP-IDF component never
sees grpc++/protobuf (FR-015).

## 2. New internal contract: the `Transport` abstraction

See [transport-interface.md](./transport-interface.md). This is an SDK-internal
C++ interface (not a wire contract) that both `LibpeerTransport` (WebRTC) and
`GrpcTransport` implement, so `VoiceSession` is transport-agnostic.

## 3. Public API: additive only

The SDK's public surface (`include/aivg/sat/`) changes **only additively**
(FR-003): new opt-in `SatelliteOptions` fields (transport selection / gRPC port /
TLS). Existing feature-020 integrations compile and run with no source change
(SC-005). The `SatEvent` surface is unchanged — gRPC maps onto existing events.

## 4. Contract-version note

This feature consumes the `0.3.0` envelope feature 021 established (it adds the
`grpc` transport the device now also speaks). No further envelope bump here.
