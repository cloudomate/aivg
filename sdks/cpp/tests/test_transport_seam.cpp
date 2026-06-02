// libaivg-sat — transport seam test (feature 022, T007).
//
// Drives a real VoiceSession against an in-process FakeTransport (no libpeer,
// no grpc, no hardware). Proves the seam: mic PCM flows to the transport, and
// downstream audio the transport surfaces reaches the playback callback.
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdio>
#include <memory>
#include <thread>
#include <vector>

#include "aivg/sat/audio.hpp"
#include "transport/transport.hpp"
#include "voice_session.hpp"

using namespace aivg::sat::detail;
using aivg::sat::AudioInputCallback;
using aivg::sat::AudioOutputCallback;
using namespace std::chrono_literals;

class FakeTransport : public Transport {
 public:
  bool begin() override { ready_.store(true); return true; }
  const std::string& session_id() const noexcept override { return sid_; }
  std::size_t mic_frame_samples() const noexcept override { return 320; }
  void send_mic(const std::int16_t*, std::size_t n) override {
    mic_frames_.fetch_add(1);
    mic_samples_.fetch_add(static_cast<long>(n));
  }
  bool ready() const noexcept override { return ready_.load(); }
  void stop() override { ready_.store(false); }
  void set_on_remote_audio(OnRemoteAudio cb) override { on_audio_ = std::move(cb); }
  void set_on_event(OnEvent cb) override { on_event_ = std::move(cb); }

  // Test hooks — simulate the gateway pushing audio/events down.
  void emit_pcm(const std::int16_t* pcm, std::size_t samples) {
    if (on_audio_)
      on_audio_(reinterpret_cast<const std::uint8_t*>(pcm), samples * sizeof(std::int16_t),
                Codec::PcmS16le16k);
  }
  void emit_event(const TransportEvent& te) {
    if (on_event_) on_event_(te);
  }

  std::atomic<int> mic_frames_{0};
  std::atomic<long> mic_samples_{0};

 private:
  std::string sid_ = "fake-sess";
  std::atomic<bool> ready_{false};
  OnRemoteAudio on_audio_;
  OnEvent on_event_;
};

int main() {
  auto ft = std::make_unique<FakeTransport>();
  FakeTransport* raw = ft.get();

  std::atomic<long> played{0};
  AudioInputCallback in = [](std::int16_t* buf, std::size_t n) -> std::size_t {
    for (std::size_t i = 0; i < n; ++i) buf[i] = 0x10;
    return n;
  };
  AudioOutputCallback out = [&](const std::int16_t*, std::size_t n) {
    played.fetch_add(static_cast<long>(n));
  };

  VoiceSession vs(std::move(ft), in, out);
  assert(vs.begin() && "VoiceSession.begin() over FakeTransport must succeed");
  assert(vs.session_id() == "fake-sess" && "session id comes from the transport");
  vs.unmute();

  // Wait for the mic pump (20 ms cadence) to push a few frames.
  for (int i = 0; i < 30 && raw->mic_frames_.load() < 2; ++i)
    std::this_thread::sleep_for(20ms);
  assert(raw->mic_frames_.load() >= 1 && "mic frames must flow to the transport");
  assert(raw->mic_samples_.load() == raw->mic_frames_.load() * 320 &&
         "each frame is mic_frame_samples() long");

  // Downstream PCM passthrough must reach the playback callback.
  std::vector<std::int16_t> pcm(160, 0x20);
  raw->emit_pcm(pcm.data(), pcm.size());
  for (int i = 0; i < 20 && played.load() == 0; ++i) std::this_thread::sleep_for(5ms);
  assert(played.load() == static_cast<long>(pcm.size()) &&
         "downstream PCM must reach playback unchanged");

  // Transport events forward through VoiceSession::set_on_event (T015).
  std::atomic<int> transcripts{0}, drops{0};
  std::string last_transcript;
  vs.set_on_event([&](const TransportEvent& te) {
    if (te.kind == TransportEvent::Kind::Transcript) {
      transcripts.fetch_add(1);
      last_transcript = te.text;
    } else if (te.kind == TransportEvent::Kind::StreamDropped) {
      drops.fetch_add(1);
    }
  });
  {
    TransportEvent t;
    t.kind = TransportEvent::Kind::Transcript;
    t.text = "partial hi";
    t.is_final = false;
    raw->emit_event(t);
    TransportEvent d;
    d.kind = TransportEvent::Kind::StreamDropped;
    d.reason = "test";
    raw->emit_event(d);
  }
  assert(transcripts.load() == 1 && last_transcript == "partial hi" &&
         "transcript event must forward through the seam");
  assert(drops.load() == 1 && "stream-drop event must forward through the seam");

  vs.end();
  std::printf("test_transport_seam: OK (mic_frames=%d played=%ld transcripts=%d drops=%d)\n",
              raw->mic_frames_.load(), played.load(), transcripts.load(), drops.load());
  return 0;
}
