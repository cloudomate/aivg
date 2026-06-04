// libaivg-sat — gRPC voice-plane transport (feature 022, US1).
#include "transport/grpc_transport.hpp"

#include <chrono>
#include <mutex>
#include <utility>

#include <grpcpp/grpcpp.h>

#include "aivg/satellite/v1/audio.grpc.pb.h"
#include "aivg/satellite/v1/audio.pb.h"

namespace aivg::sat::detail {

namespace pb = ::aivg::satellite::v1;

namespace {

pb::Codec to_proto_codec(Codec c) {
  switch (c) {
    case Codec::Opus:        return pb::CODEC_OPUS;
    case Codec::PcmS16le16k: return pb::CODEC_PCM_S16LE_16K;
    default:                 return pb::CODEC_UNSPECIFIED;
  }
}

Codec from_proto_codec(pb::Codec c) {
  switch (c) {
    case pb::CODEC_OPUS:          return Codec::Opus;
    case pb::CODEC_PCM_S16LE_16K: return Codec::PcmS16le16k;
    default:                      return Codec::Unspecified;
  }
}

std::uint64_t now_ns() {
  return static_cast<std::uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(
          std::chrono::steady_clock::now().time_since_epoch())
          .count());
}

}  // namespace

struct GrpcTransport::Impl {
  std::shared_ptr<grpc::Channel> channel;
  std::unique_ptr<pb::Audio::Stub> stub;
  grpc::ClientContext ctx;
  std::unique_ptr<grpc::ClientReaderWriter<pb::ClientFrame, pb::ServerFrame>> stream;
  std::mutex write_mu;  // serializes writes (mic pump + client signals + header)
};

GrpcTransport::GrpcTransport(GrpcTransportOptions opts)
    : opts_(std::move(opts)), impl_(std::make_unique<Impl>()) {}

GrpcTransport::~GrpcTransport() { stop(); }

bool GrpcTransport::begin() {
  std::shared_ptr<grpc::ChannelCredentials> creds;
  if (opts_.use_tls) {
    // Fleet posture (FR-014): mutual TLS. Never silently downgrade — if the
    // caller asked for TLS we use SslCredentials with the supplied material.
    grpc::SslCredentialsOptions ssl;
    ssl.pem_root_certs = opts_.ca_pem;
    ssl.pem_private_key = opts_.key_pem;
    ssl.pem_cert_chain = opts_.cert_pem;
    creds = grpc::SslCredentials(ssl);
  } else {
    // Trusted-LAN default.
    creds = grpc::InsecureChannelCredentials();
  }
  impl_->channel = grpc::CreateChannel(opts_.target, creds);
  impl_->stub = pb::Audio::NewStub(impl_->channel);
  impl_->stream = impl_->stub->Stream(&impl_->ctx);
  if (!impl_->stream) return false;

  // First ClientFrame MUST be the SessionHeader (FR-007).
  pb::ClientFrame hdr;
  auto* sh = hdr.mutable_session();
  sh->set_session_id(opts_.session_id);
  // Advertise the preferred downstream codec best-first, then 16 kHz PCM as a
  // guaranteed fallback so an older gateway that can't produce the preferred
  // codec (e.g. Opus) still serves working audio (feature 024).
  sh->add_downstream_codec_pref(to_proto_codec(opts_.downstream_pref));
  if (opts_.downstream_pref != Codec::PcmS16le16k) {
    sh->add_downstream_codec_pref(pb::CODEC_PCM_S16LE_16K);
  }
  // Feature 025: advertise the upstream (mic) codec the device will send,
  // best-first, with raw 16 kHz PCM as the guaranteed fallback.
  sh->add_upstream_codec_pref(to_proto_codec(opts_.upstream_pref));
  if (opts_.upstream_pref != Codec::PcmS16le16k) {
    sh->add_upstream_codec_pref(pb::CODEC_PCM_S16LE_16K);
  }
  {
    std::lock_guard<std::mutex> lk(impl_->write_mu);
    if (!impl_->stream->Write(hdr)) return false;
  }
  ready_.store(true);
  reader_ = std::thread([this] { reader_loop(); });
  return true;
}

void GrpcTransport::send_mic(const std::int16_t* pcm16, std::size_t samples) {
  if (!ready_.load() || stopping_.load() || pcm16 == nullptr || samples == 0) return;
  pb::ClientFrame f;
  if (opts_.upstream_pref == Codec::Opus) {
    // Feature 025: Opus-encode the 48 kHz mic frame on-device (960 samples ->
    // one packet) and send the `opus` arm — compressed uplink, no decimation.
    auto packet = mic_enc_.encode(pcm16, samples);
    if (packet.empty()) return;  // encode error -> skip this frame
    auto* op = f.mutable_opus();
    op->set_payload(reinterpret_cast<const char*>(packet.data()), packet.size());
    op->set_ts_ns(now_ns());
  } else {
    // Raw 16 kHz s16le PCM (default/fallback).
    auto* pcm = f.mutable_pcm();
    pcm->set_samples(reinterpret_cast<const char*>(pcm16), samples * sizeof(std::int16_t));
    pcm->set_ts_ns(now_ns());
  }
  std::lock_guard<std::mutex> lk(impl_->write_mu);
  if (impl_->stream) impl_->stream->Write(f);
}

void GrpcTransport::send_signal(ClientSignal sig) {
  if (!ready_.load() || stopping_.load()) return;
  pb::ClientFrame f;
  auto* ev = f.mutable_event();
  switch (sig) {
    case ClientSignal::WakeFired:      ev->set_kind(pb::ClientEvent::WAKE_FIRED); break;
    case ClientSignal::EndOfUtterance: ev->set_kind(pb::ClientEvent::END_OF_UTTERANCE); break;
    case ClientSignal::BargeInStart:   ev->set_kind(pb::ClientEvent::BARGE_IN_START); break;
  }
  std::lock_guard<std::mutex> lk(impl_->write_mu);
  if (impl_->stream) impl_->stream->Write(f);
}

void GrpcTransport::reader_loop() {
  pb::ServerFrame sf;
  while (impl_->stream && impl_->stream->Read(&sf)) {
    switch (sf.body_case()) {
      case pb::ServerFrame::kAudio: {
        const auto& a = sf.audio();
        if (on_audio_ && !a.payload().empty()) {
          on_audio_(reinterpret_cast<const std::uint8_t*>(a.payload().data()),
                    a.payload().size(), from_proto_codec(a.codec()));
        }
        break;
      }
      case pb::ServerFrame::kEvent: {
        if (on_event_) {
          TransportEvent te{};
          switch (sf.event().kind()) {
            case pb::ServerEvent::SPEAKING_STARTED: te.kind = TransportEvent::Kind::SpeakingStarted; break;
            case pb::ServerEvent::SPEAKING_ENDED:   te.kind = TransportEvent::Kind::SpeakingEnded; break;
            case pb::ServerEvent::VAD_DETECTED:     te.kind = TransportEvent::Kind::VadDetected; break;
            default: continue;  // KIND_UNSPECIFIED — ignore
          }
          on_event_(te);
        }
        break;
      }
      case pb::ServerFrame::kTranscript: {
        if (on_event_) {
          TransportEvent te{};
          te.kind = TransportEvent::Kind::Transcript;
          te.text = sf.transcript().text();
          te.is_final = sf.transcript().is_final();
          on_event_(te);
        }
        break;
      }
      default:
        break;  // BODY_NOT_SET
    }
    sf.Clear();
  }
  ready_.store(false);
  // Stream ended. If we didn't ask for it, surface a drop (FR-013).
  if (!stopping_.load() && on_event_) {
    TransportEvent te{};
    te.kind = TransportEvent::Kind::StreamDropped;
    te.reason = "audio stream closed by peer";
    on_event_(te);
  }
}

void GrpcTransport::stop() {
  if (stopping_.exchange(true)) {
    if (reader_.joinable()) reader_.join();
    return;
  }
  ready_.store(false);
  if (impl_->stream) {
    {
      std::lock_guard<std::mutex> lk(impl_->write_mu);
      impl_->stream->WritesDone();
    }
    impl_->ctx.TryCancel();  // unblock a pending Read in the reader thread
  }
  if (reader_.joinable()) reader_.join();
  if (impl_->stream) impl_->stream->Finish();
}

}  // namespace aivg::sat::detail
