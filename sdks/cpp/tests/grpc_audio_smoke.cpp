// libaivg-sat — live gRPC audio smoke (feature 022, T009).
//
// Drives the real GrpcTransport against a running gateway-side
// aivg.satellite.v1.Audio/Stream server (feature 021). NOT a ctest — it needs
// a live gateway. Streams a short utterance and asserts reply audio comes back.
//
// Usage:  grpc_audio_smoke [host:port]   (default host.docker.internal:8645)
#include <atomic>
#include <chrono>
#include <cstdio>
#include <string>
#include <thread>
#include <vector>

#include "transport/grpc_transport.hpp"

using namespace aivg::sat::detail;
using namespace std::chrono_literals;

int main(int argc, char** argv) {
  const std::string target = (argc > 1) ? argv[1] : "host.docker.internal:8645";

  GrpcTransportOptions opts;
  opts.target = target;
  opts.session_id = "cpp-smoke-sess";
  GrpcTransport t(opts);

  std::atomic<int> audio_frames{0};
  std::atomic<long> audio_bytes{0};
  std::atomic<bool> speaking{false};
  std::vector<std::string> transcripts;

  t.set_on_remote_audio([&](const std::uint8_t*, std::size_t n, Codec) {
    if (n > 0) { audio_frames.fetch_add(1); audio_bytes.fetch_add(static_cast<long>(n)); }
  });
  t.set_on_event([&](const TransportEvent& ev) {
    if (ev.kind == TransportEvent::Kind::SpeakingStarted) speaking.store(true);
    else if (ev.kind == TransportEvent::Kind::Transcript) transcripts.push_back(ev.text);
  });

  std::printf("connecting to %s ...\n", target.c_str());
  if (!t.begin()) {
    std::fprintf(stderr, "FAIL: GrpcTransport.begin() — is the gateway up at %s?\n",
                 target.c_str());
    return 1;
  }

  // Stream ~200 ms of audio (the echo gateway fires the turn after 5 frames),
  // then signal end-of-utterance.
  std::vector<std::int16_t> frame(320, 0x1234);  // 20 ms @ 16 kHz
  for (int i = 0; i < 10; ++i) {
    t.send_mic(frame.data(), frame.size());
    std::this_thread::sleep_for(20ms);
  }
  t.send_signal(ClientSignal::EndOfUtterance);

  // Wait (bounded) for reply audio.
  for (int i = 0; i < 300 && audio_frames.load() == 0; ++i) std::this_thread::sleep_for(20ms);

  t.stop();

  std::printf("audio_frames=%d audio_bytes=%ld speaking=%d transcripts=%zu\n",
              audio_frames.load(), audio_bytes.load(), speaking.load() ? 1 : 0,
              transcripts.size());
  if (audio_frames.load() <= 0) {
    std::fprintf(stderr, "FAIL: no reply audio received from the gateway\n");
    return 1;
  }
  std::printf("grpc_audio_smoke: OK — reply audio received over a live gRPC Audio.Stream\n");
  return 0;
}
