// libaivg-sat — gRPC transport in-process round-trip test (feature 022, US1).
//
// Stands up a fake Audio.Stream server in-process and drives a real
// GrpcTransport against it: header → speaking_started + transcript; pcm up;
// end-of-utterance → reply AudioChunk + speaking_ended. Asserts the transport
// surfaces remote audio (with codec) and events. No hardware, no gateway.
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdio>
#include <memory>
#include <string>
#include <thread>
#include <vector>

#include <grpcpp/grpcpp.h>

#include "aivg/satellite/v1/audio.grpc.pb.h"
#include "aivg/satellite/v1/audio.pb.h"
#include "transport/grpc_transport.hpp"

namespace pb = ::aivg::satellite::v1;
using namespace aivg::sat::detail;

class FakeAudio final : public pb::Audio::Service {
 public:
  grpc::Status Stream(
      grpc::ServerContext*,
      grpc::ServerReaderWriter<pb::ServerFrame, pb::ClientFrame>* stream) override {
    pb::ClientFrame cf;
    while (stream->Read(&cf)) {
      if (cf.has_session()) {
        session_id = cf.session().session_id();
        pb::ServerFrame s;
        s.mutable_event()->set_kind(pb::ServerEvent::SPEAKING_STARTED);
        stream->Write(s);
        pb::ServerFrame t;
        t.mutable_transcript()->set_text("hello world");
        t.mutable_transcript()->set_is_final(true);
        stream->Write(t);
      } else if (cf.has_pcm()) {
        pcm_frames++;
      } else if (cf.has_event() &&
                 cf.event().kind() == pb::ClientEvent::END_OF_UTTERANCE) {
        pb::ServerFrame a;
        auto* au = a.mutable_audio();
        au->set_codec(pb::CODEC_PCM_S16LE_16K);
        au->set_payload(std::string(640, '\x01'));
        au->set_seq(1);
        stream->Write(a);
        pb::ServerFrame e;
        e.mutable_event()->set_kind(pb::ServerEvent::SPEAKING_ENDED);
        stream->Write(e);
        break;  // end of turn
      }
      cf.Clear();
    }
    return grpc::Status::OK;
  }

  std::string session_id;
  std::atomic<int> pcm_frames{0};
};

int main() {
  FakeAudio svc;
  int port = 0;
  grpc::ServerBuilder builder;
  builder.AddListeningPort("127.0.0.1:0", grpc::InsecureServerCredentials(), &port);
  builder.RegisterService(&svc);
  std::unique_ptr<grpc::Server> server = builder.BuildAndStart();
  assert(server && port > 0);

  std::atomic<int> audio_frames{0};
  std::atomic<bool> got_speaking_started{false}, got_speaking_ended{false};
  std::vector<std::string> transcripts;
  std::atomic<Codec> last_codec{Codec::Unspecified};

  GrpcTransportOptions opts;
  opts.target = "127.0.0.1:" + std::to_string(port);
  opts.session_id = "sess-1";
  GrpcTransport t(opts);
  t.set_on_remote_audio([&](const std::uint8_t*, std::size_t n, Codec c) {
    if (n > 0) { audio_frames++; last_codec.store(c); }
  });
  t.set_on_event([&](const TransportEvent& ev) {
    switch (ev.kind) {
      case TransportEvent::Kind::SpeakingStarted: got_speaking_started = true; break;
      case TransportEvent::Kind::SpeakingEnded:   got_speaking_ended = true; break;
      case TransportEvent::Kind::Transcript:      transcripts.push_back(ev.text); break;
      default: break;
    }
  });

  bool ok = t.begin();
  assert(ok && "GrpcTransport.begin() must succeed");

  // Stream a few PCM frames, then signal end-of-utterance.
  std::vector<std::int16_t> frame(320, 0x1234);  // 20 ms @ 16 kHz
  for (int i = 0; i < 5; ++i) {
    t.send_mic(frame.data(), frame.size());
    std::this_thread::sleep_for(std::chrono::milliseconds(5));
  }
  t.send_signal(ClientSignal::EndOfUtterance);

  // Wait (bounded) for the reply audio to come back.
  for (int i = 0; i < 200 && audio_frames.load() == 0; ++i)
    std::this_thread::sleep_for(std::chrono::milliseconds(10));

  t.stop();
  server->Shutdown();
  server->Wait();

  // Assertions.
  assert(svc.session_id == "sess-1" && "server must receive the SessionHeader id");
  assert(svc.pcm_frames.load() >= 1 && "server must receive raw PCM frames");
  assert(audio_frames.load() >= 1 && "transport must surface reply audio");
  assert(last_codec.load() == Codec::PcmS16le16k && "codec must be surfaced (PCM)");
  assert(got_speaking_started.load() && "SpeakingStarted event must surface");
  assert(got_speaking_ended.load() && "SpeakingEnded event must surface");
  assert(transcripts.size() == 1 && transcripts[0] == "hello world" &&
         "transcript must surface on the same stream");

  std::printf("grpc_transport_inproc_test: OK (pcm_up=%d audio_down=%d transcripts=%zu)\n",
              svc.pcm_frames.load(), audio_frames.load(), transcripts.size());
  return 0;
}
