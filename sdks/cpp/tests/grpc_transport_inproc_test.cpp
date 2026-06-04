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
        for (int c : cf.session().downstream_codec_pref()) codec_prefs.push_back(c);
        for (int c : cf.session().upstream_codec_pref()) up_prefs.push_back(c);  // 025
        pb::ServerFrame s;
        s.mutable_event()->set_kind(pb::ServerEvent::SPEAKING_STARTED);
        stream->Write(s);
        pb::ServerFrame t;
        t.mutable_transcript()->set_text("hello world");
        t.mutable_transcript()->set_is_final(true);
        stream->Write(t);
      } else if (cf.has_pcm()) {
        pcm_frames++;
      } else if (cf.has_opus()) {
        opus_frames++;  // feature 025 — Opus mic arm
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
  std::atomic<int> opus_frames{0};  // feature 025 — Opus mic arms received
  std::vector<int> codec_prefs;  // advertised downstream_codec_pref (feature 024)
  std::vector<int> up_prefs;     // advertised upstream_codec_pref (feature 025)
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
  // Feature 024: the default gRPC client advertises Opus best-first, with
  // 16 kHz PCM as the guaranteed fallback.
  assert(svc.codec_prefs.size() == 2 && svc.codec_prefs[0] == pb::CODEC_OPUS &&
         svc.codec_prefs[1] == pb::CODEC_PCM_S16LE_16K &&
         "client must advertise [Opus, PCM_16K] downstream prefs");
  assert(svc.pcm_frames.load() >= 1 && "server must receive raw PCM frames");
  assert(audio_frames.load() >= 1 && "transport must surface reply audio");
  assert(last_codec.load() == Codec::PcmS16le16k && "codec must be surfaced (PCM)");
  assert(got_speaking_started.load() && "SpeakingStarted event must surface");
  assert(got_speaking_ended.load() && "SpeakingEnded event must surface");
  assert(transcripts.size() == 1 && transcripts[0] == "hello world" &&
         "transcript must surface on the same stream");
  // Feature 025: default upstream is raw PCM — the device advertises [PCM_16K]
  // and sends `pcm` frames (US2).
  assert(svc.up_prefs.size() == 1 && svc.up_prefs[0] == pb::CODEC_PCM_S16LE_16K &&
         "default upstream pref must be PCM_16K");
  assert(svc.opus_frames.load() == 0 && "default upstream must send no Opus frames");

  // --- Feature 025 / US1: upstream Opus -----------------------------------
  // A second session with upstream Opus enabled must advertise [Opus, PCM_16K]
  // and send the `opus` mic arm (mic_frame_samples()==960 → encode each frame).
  {
    FakeAudio svc2;
    int port2 = 0;
    grpc::ServerBuilder b2;
    b2.AddListeningPort("127.0.0.1:0", grpc::InsecureServerCredentials(), &port2);
    b2.RegisterService(&svc2);
    std::unique_ptr<grpc::Server> server2 = b2.BuildAndStart();
    assert(server2 && port2 > 0);

    GrpcTransportOptions o2;
    o2.target = "127.0.0.1:" + std::to_string(port2);
    o2.session_id = "sess-opus";
    o2.upstream_pref = Codec::Opus;
    GrpcTransport t2(o2);
    assert(t2.begin() && "upstream-Opus begin() must succeed");
    assert(t2.mic_frame_samples() == 960 && "Opus upstream captures at 48 kHz (960)");
    std::vector<std::int16_t> f48(960, 0x0123);  // 20 ms @ 48 kHz
    for (int i = 0; i < 5; ++i) {
      t2.send_mic(f48.data(), f48.size());
      std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
    t2.send_signal(ClientSignal::EndOfUtterance);
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    t2.stop();
    server2->Shutdown();
    server2->Wait();

    assert(svc2.up_prefs.size() == 2 && svc2.up_prefs[0] == pb::CODEC_OPUS &&
           svc2.up_prefs[1] == pb::CODEC_PCM_S16LE_16K &&
           "client must advertise [Opus, PCM_16K] upstream prefs");
    assert(svc2.opus_frames.load() >= 1 && "device must send the Opus mic arm");
    assert(svc2.pcm_frames.load() == 0 && "Opus upstream must send no raw PCM");
    std::printf("  upstream Opus: opus_up=%d\n", svc2.opus_frames.load());
  }

  std::printf("grpc_transport_inproc_test: OK (pcm_up=%d audio_down=%d transcripts=%zu)\n",
              svc.pcm_frames.load(), audio_frames.load(), transcripts.size());
  return 0;
}
