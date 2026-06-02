// libaivg-sat — gRPC voice-plane transport (feature 022, US1, internal).
//
// Implements the abstract Transport seam over the gateway's
// `aivg.satellite.v1.Audio/Stream` bidi RPC: one stream per voice session —
// raw 16 kHz PCM up (no on-device Opus encode), codec-tagged audio +
// transcripts + turn events down. POSIX/RPi tier only (gated by
// AIVG_SAT_ENABLE_GRPC). grpc++ is confined to the .cpp via a pimpl so this
// header stays dependency-light.
#ifndef AIVG_SAT_TRANSPORT_GRPC_TRANSPORT_HPP
#define AIVG_SAT_TRANSPORT_GRPC_TRANSPORT_HPP

#include <atomic>
#include <cstdint>
#include <memory>
#include <string>
#include <thread>

#include "transport/transport.hpp"

namespace aivg::sat::detail {

struct GrpcTransportOptions {
  std::string target;          // "host:port" of the gRPC audio plane
  std::string session_id;      // adoption/minted id; sent in SessionHeader
  bool use_tls = false;        // insecure (trusted LAN) vs SSL/mTLS (fleet)
  std::string ca_pem;          // mTLS material (when use_tls)
  std::string cert_pem;
  std::string key_pem;
  Codec downstream_pref = Codec::PcmS16le16k;
};

// A client lifecycle signal pushed up the audio stream (FR maps to proto
// ClientEvent.Kind). Kept transport-neutral on the abstract interface as a
// no-op default; GrpcTransport overrides it.
enum class ClientSignal { WakeFired, EndOfUtterance, BargeInStart };

class GrpcTransport : public Transport {
 public:
  explicit GrpcTransport(GrpcTransportOptions opts);
  ~GrpcTransport() override;

  GrpcTransport(const GrpcTransport&) = delete;
  GrpcTransport& operator=(const GrpcTransport&) = delete;

  bool begin() override;
  const std::string& session_id() const noexcept override { return opts_.session_id; }
  // 16 kHz * 20 ms = 320 samples per upstream PcmChunk.
  std::size_t mic_frame_samples() const noexcept override { return 320; }
  void send_mic(const std::int16_t* pcm16, std::size_t samples) override;
  bool ready() const noexcept override { return ready_.load(); }
  void stop() override;
  void set_on_remote_audio(OnRemoteAudio cb) override { on_audio_ = std::move(cb); }
  void set_on_event(OnEvent cb) override { on_event_ = std::move(cb); }

  // Push a client lifecycle signal (wake / end-of-utterance / barge-in) up
  // the audio stream (FR-012/T013).
  void send_signal(ClientSignal sig);

 private:
  struct Impl;                 // holds grpc++ channel/stub/stream/context
  void reader_loop();

  GrpcTransportOptions opts_;
  std::unique_ptr<Impl> impl_;
  std::thread reader_;
  std::atomic<bool> ready_{false};
  std::atomic<bool> stopping_{false};
  OnRemoteAudio on_audio_;
  OnEvent on_event_;
};

}  // namespace aivg::sat::detail

#endif  // AIVG_SAT_TRANSPORT_GRPC_TRANSPORT_HPP
