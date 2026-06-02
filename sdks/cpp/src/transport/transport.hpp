// libaivg-sat — abstract voice-plane transport seam (feature 022, internal).
//
// Both LibpeerTransport (WebRTC) and GrpcTransport implement this, so
// VoiceSession drives either without knowing which. The seam is at the
// AUDIO + LIFECYCLE + EVENT altitude — deliberately NO SDP/offer/answer
// methods (those are WebRTC-specific internals of LibpeerTransport::begin),
// which is what lets gRPC (no offer/answer) implement it cleanly.
//
// Constitution III (v2.1.0, transport-neutral): a per-session voice
// connection, realized by WebRTC or gRPC Audio.Stream.
#ifndef AIVG_SAT_TRANSPORT_TRANSPORT_HPP
#define AIVG_SAT_TRANSPORT_TRANSPORT_HPP

#include <cstddef>
#include <cstdint>
#include <functional>
#include <string>

namespace aivg::sat::detail {

// Downstream audio codec — mirrors proto `aivg.satellite.v1.Codec`. Kept as a
// plain enum here so the WebRTC path needs no protobuf dependency.
enum class Codec { Unspecified, Opus, PcmS16le16k };

// A discrete, call-scoped event surfaced by a transport. VoiceSession maps
// these onto the SDK's public `SatEvent` (no new public event type — FR-006).
struct TransportEvent {
  enum class Kind {
    SpeakingStarted,
    SpeakingEnded,
    VadDetected,
    Transcript,
    StreamDropped,
  };
  Kind kind;
  std::string text;        // Transcript text (else empty)
  bool is_final = false;   // Transcript finality
  std::string reason;      // StreamDropped reason (else empty)
};

class Transport {
 public:
  // Downstream audio: (payload, size, codec). WebRTC always delivers Opus;
  // gRPC delivers whatever codec the gateway stamped on the AudioChunk.
  using OnRemoteAudio =
      std::function<void(const std::uint8_t* payload, std::size_t size, Codec codec)>;
  using OnEvent = std::function<void(const TransportEvent& ev)>;

  virtual ~Transport() = default;

  // Establish the voice link. Connection-establishment specifics (WebRTC
  // offer/answer signaling, or opening the gRPC Audio.Stream + SessionHeader)
  // are internal. Returns false if the link could not be established.
  virtual bool begin() = 0;

  // The session id for this voice link — valid only after a successful
  // begin(). WebRTC mints it from signaling; gRPC carries the adoption id.
  virtual const std::string& session_id() const noexcept = 0;

  // Samples per 20 ms mic frame this transport expects (= rate * 0.02). The
  // capture rate is transport-dependent: WebRTC/Opus is 48 kHz (960), the gRPC
  // PCM plane is 16 kHz (320). VoiceSession pulls this many per pump tick.
  virtual std::size_t mic_frame_samples() const noexcept = 0;

  // Push one frame of captured mic audio (PCM16 mono @ mic_frame_samples()).
  // WebRTC Opus-encodes internally; gRPC sends raw PCM (no on-device encode).
  // Frames pushed before ready() may be dropped (bounded — no backlog).
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

#endif  // AIVG_SAT_TRANSPORT_TRANSPORT_HPP
