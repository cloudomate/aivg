# Internal Contract: the `Transport` abstraction (feature 022)

An SDK-internal C++ interface (`sdks/cpp/src/transport/transport.hpp`) that both
`LibpeerTransport` (WebRTC) and `GrpcTransport` (gRPC) implement, so
`VoiceSession` drives either without knowing which. This is the seam the feature
introduces (research R-1); it is not a wire contract.

## Interface

```cpp
namespace aivg::sat::detail {

enum class Codec { Unspecified, Opus, PcmS16le16k };  // mirrors proto Codec

struct TransportEvent {
  enum class Kind { SpeakingStarted, SpeakingEnded, VadDetected,
                    Transcript, StreamDropped };
  Kind kind;
  std::string text;       // Transcript text (else empty)
  bool is_final = false;  // Transcript finality
  std::string reason;     // StreamDropped reason (else empty)
};

class Transport {
 public:
  using OnRemoteAudio = std::function<void(const std::uint8_t* payload,
                                           std::size_t size, Codec codec)>;
  using OnEvent       = std::function<void(const TransportEvent&)>;

  virtual ~Transport() = default;

  // Open the voice link for `session_id`. Blocking-or-async per impl;
  // returns false if the link could not be established.
  virtual bool begin(const std::string& session_id) = 0;

  // Push one frame of captured mic audio (16 kHz s16le mono). Implementations
  // gate on ready(); frames before ready() may be dropped (bounded).
  virtual void send_mic(const std::int16_t* pcm16, std::size_t samples) = 0;

  // True once it is safe to pump mic audio (WebRTC: DTLS-SRTP complete;
  // gRPC: stream open and SessionHeader sent).
  virtual bool ready() const noexcept = 0;

  // Tear down the voice link. Idempotent.
  virtual void stop() = 0;

  virtual void set_on_remote_audio(OnRemoteAudio cb) = 0;
  virtual void set_on_event(OnEvent cb) = 0;
};

}  // namespace aivg::sat::detail
```

## Contract obligations

| Obligation | WebRTC (`LibpeerTransport`) | gRPC (`GrpcTransport`) |
|---|---|---|
| `begin()` | offer → POST `/webrtc/offer` → answer → pump (existing) | open `Audio.Stream`; send `SessionHeader{session_id, codec_pref}` |
| `send_mic()` | Opus-encode → `send_opus` (existing) | wrap raw PCM in `ClientFrame.pcm` (no encode, R-3) |
| `ready()` | `is_completed()` (DTLS-SRTP) | stream open + header acked |
| downstream | libpeer Opus track → `on_remote_audio(…, Opus)` | `ServerFrame.audio` → `on_remote_audio(…, codec)` |
| events | (n/a today) | `ServerFrame.event`/`transcript` → `on_event` |
| drop | peer failed → `on_event(StreamDropped)` | stream error → `on_event(StreamDropped)` |

## Notes

- The interface is at the **audio + lifecycle** altitude — deliberately **no**
  SDP/offer/answer methods (those are WebRTC-specific internals of
  `LibpeerTransport::begin`). This is what lets gRPC (which has no offer/answer)
  implement the same seam cleanly (R-1).
- `VoiceSession` maps `TransportEvent` → the SDK's public `SatEvent` so the
  application sees identical events on either transport (FR-006). No new public
  event type is introduced.
- The refactor of `LibpeerTransport` to implement this interface is a pure
  re-shape with **no behaviour change** — existing WebRTC tests/integrations
  must stay green (SC-005).
