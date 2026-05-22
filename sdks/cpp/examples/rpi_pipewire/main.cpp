// libaivg-sat — RPi reference satellite: PipeWire (seeed ReSpeaker) audio +
// openWakeWord-gated streaming (feature 020 example).
//
// Architecture:
//   PipeWire capture (seeed mic, S16/mono/48k) --> mic_ring --> SDK audio_input
//                                              \--> WakeWord detector
//   SDK audio_output --> spk_ring --> PipeWire playback (seeed speaker)
//
// The SDK voice session is LONG-LIVED (FR-010). The device wake word only
// *gates* the upstream mic (unmute/mute) — the gateway still owns
// endpointing/STT/agent/TTS (Constitution Principle I). On wake, we unmute;
// when the gateway finishes the turn (gateway_state -> idle), we mute again.
//
// PipeWire integration is a reference; production tuning (xruns, latency,
// device targeting) is the integrator's job. openWakeWord inference is a
// documented seam (see WakeWordDetector) — drop in the ONNX model runner.
//
// Build: see CMakeLists.txt (links aivg::sat + libpipewire-0.3).
// Run:   rpi_pipewire ws://<gw>:8643 http://<gw>:8644 <device_id> [seeed_node]

#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <deque>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <variant>

#include <pipewire/pipewire.h>
#include <spa/param/audio/format-utils.h>

#include <aivg/sat/satellite.hpp>

using namespace std::chrono_literals;

namespace {

constexpr int kRate = 48000;     // SDK callback boundary: PCM16 mono 48 kHz
constexpr int kChannels = 1;

// --- Simple thread-safe PCM ring (mutex for clarity; swap for lock-free in prod) ---
class PcmRing {
 public:
  void write(const std::int16_t* p, std::size_t n) {
    std::lock_guard<std::mutex> lk(m_);
    buf_.insert(buf_.end(), p, p + n);
    if (buf_.size() > kRate * 4) buf_.erase(buf_.begin(), buf_.end() - kRate * 2);  // cap ~2s
  }
  std::size_t read(std::int16_t* p, std::size_t n) {
    std::lock_guard<std::mutex> lk(m_);
    std::size_t got = std::min(n, buf_.size());
    for (std::size_t i = 0; i < got; ++i) p[i] = buf_[i];
    buf_.erase(buf_.begin(), buf_.begin() + got);
    return got;
  }
 private:
  std::mutex m_;
  std::deque<std::int16_t> buf_;
};

// --- openWakeWord seam -------------------------------------------------------
// Replace `detect()` with a real openWakeWord runner: feed 16 kHz mono frames
// to the openWakeWord ONNX models (melspectrogram -> embedding -> wakeword)
// via onnxruntime, and return true when the score crosses your threshold.
// This placeholder uses a crude energy gate so the example builds standalone.
class WakeWordDetector {
 public:
  // Feed 48 kHz mono PCM (downsample to 16 kHz for openWakeWord internally).
  // Returns true once on a wake-word detection.
  bool detect(const std::int16_t* pcm, std::size_t frames) {
    // TODO(integrator): run openWakeWord here. Placeholder = sustained energy.
    long sum = 0;
    for (std::size_t i = 0; i < frames; ++i) sum += std::abs(pcm[i]);
    long avg = frames ? sum / static_cast<long>(frames) : 0;
    loud_ = avg > 1500 ? loud_ + 1 : 0;
    if (loud_ > 8) { loud_ = 0; return true; }  // ~placeholder trigger
    return false;
  }
 private:
  int loud_ = 0;
};

// --- PipeWire plumbing -------------------------------------------------------
struct PwAudio {
  pw_thread_loop* loop = nullptr;
  pw_stream* capture = nullptr;
  pw_stream* playback = nullptr;
  PcmRing* mic = nullptr;          // capture -> here
  PcmRing* spk = nullptr;          // here -> playback
  WakeWordDetector* wake = nullptr;
  std::atomic<bool>* wake_hit = nullptr;
};

void on_capture_process(void* data) {
  auto* a = static_cast<PwAudio*>(data);
  pw_buffer* b = pw_stream_dequeue_buffer(a->capture);
  if (!b) return;
  spa_buffer* sb = b->buffer;
  if (sb->datas[0].data) {
    auto* pcm = static_cast<std::int16_t*>(sb->datas[0].data);
    std::size_t n = sb->datas[0].chunk->size / sizeof(std::int16_t);
    a->mic->write(pcm, n);
    if (a->wake->detect(pcm, n)) a->wake_hit->store(true);
  }
  pw_stream_queue_buffer(a->capture, b);
}

void on_playback_process(void* data) {
  auto* a = static_cast<PwAudio*>(data);
  pw_buffer* b = pw_stream_dequeue_buffer(a->playback);
  if (!b) return;
  spa_buffer* sb = b->buffer;
  auto* out = static_cast<std::int16_t*>(sb->datas[0].data);
  std::size_t want = sb->datas[0].maxsize / sizeof(std::int16_t);
  std::size_t got = a->spk->read(out, want);
  std::memset(out + got, 0, (want - got) * sizeof(std::int16_t));  // pad silence
  sb->datas[0].chunk->offset = 0;
  sb->datas[0].chunk->stride = sizeof(std::int16_t) * kChannels;
  sb->datas[0].chunk->size = want * sizeof(std::int16_t);
  pw_stream_queue_buffer(a->playback, b);
}

const pw_stream_events kCaptureEvents = [] {
  pw_stream_events e{};
  e.version = PW_VERSION_STREAM_EVENTS;
  e.process = on_capture_process;
  return e;
}();
const pw_stream_events kPlaybackEvents = [] {
  pw_stream_events e{};
  e.version = PW_VERSION_STREAM_EVENTS;
  e.process = on_playback_process;
  return e;
}();

pw_stream* make_stream(pw_thread_loop* loop, const char* name, pw_direction dir,
                       const pw_stream_events* ev, void* data, const char* target_node) {
  auto* props = pw_properties_new(PW_KEY_MEDIA_TYPE, "Audio", PW_KEY_MEDIA_CATEGORY,
                                  dir == PW_DIRECTION_INPUT ? "Capture" : "Playback",
                                  PW_KEY_MEDIA_ROLE, "Communication", nullptr);
  if (target_node && *target_node) pw_properties_set(props, PW_KEY_TARGET_OBJECT, target_node);
  pw_stream* s = pw_stream_new_simple(pw_thread_loop_get_loop(loop), name, props, ev, data);

  std::uint8_t buf[1024];
  spa_pod_builder pb = SPA_POD_BUILDER_INIT(buf, sizeof(buf));
  spa_audio_info_raw info{};
  info.format = SPA_AUDIO_FORMAT_S16;
  info.rate = kRate;
  info.channels = kChannels;
  const spa_pod* params[1] = {spa_format_audio_raw_build(&pb, SPA_PARAM_EnumFormat, &info)};
  pw_stream_connect(s, dir, PW_ID_ANY,
                    static_cast<pw_stream_flags>(PW_STREAM_FLAG_AUTOCONNECT |
                                                 PW_STREAM_FLAG_MAP_BUFFERS |
                                                 PW_STREAM_FLAG_RT_PROCESS),
                    params, 1);
  return s;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc < 4) {
    std::printf("usage: %s ws://<gw>:8643 http://<gw>:8644 <device_id> [seeed_node]\n", argv[0]);
    return 2;
  }
  std::string gw = argv[1], sig = argv[2], dev = argv[3];
  std::string node = argc > 4 ? argv[4] : "";  // e.g. seeed source node name

  PcmRing mic_ring, spk_ring;
  WakeWordDetector wake;
  std::atomic<bool> wake_hit{false};

  // --- PipeWire: capture (seeed mic) + playback (seeed speaker) ---
  pw_init(&argc, &argv);
  PwAudio pa;
  pa.loop = pw_thread_loop_new("aivg-audio", nullptr);
  pa.mic = &mic_ring; pa.spk = &spk_ring; pa.wake = &wake; pa.wake_hit = &wake_hit;
  pw_thread_loop_lock(pa.loop);
  pa.capture = make_stream(pa.loop, "aivg-mic", PW_DIRECTION_INPUT, &kCaptureEvents, &pa,
                           node.c_str());
  pa.playback = make_stream(pa.loop, "aivg-spk", PW_DIRECTION_OUTPUT, &kPlaybackEvents, &pa,
                            node.c_str());
  pw_thread_loop_unlock(pa.loop);
  pw_thread_loop_start(pa.loop);

  // --- SDK wiring ---
  std::atomic<std::string*> gw_state{nullptr};
  std::atomic<bool> turn_active{false};
  aivg::sat::SatelliteOptions opts;
  opts.gateway_url = gw;
  opts.signaling_url = sig;
  opts.device_id = dev;
  opts.device_name = "rpi-pipewire";
  opts.device_type = "linux";
  opts.firmware_version = "0.1.0";
  // Mic: always stream (silence when idle) so the gateway VAD can endpoint.
  opts.audio_input = [&](std::int16_t* buf, std::size_t frames) -> std::size_t {
    std::size_t got = mic_ring.read(buf, frames);
    if (got < frames) std::memset(buf + got, 0, (frames - got) * sizeof(std::int16_t));
    return frames;
  };
  // Speaker: hand reply audio to PipeWire playback.
  opts.audio_output = [&](const std::int16_t* buf, std::size_t frames) {
    spk_ring.write(buf, frames);
  };
  opts.on_event = [&](const aivg::sat::SatEvent& ev) {
    using namespace aivg::sat;
    if (auto* g = std::get_if<GatewayStatePayload>(&ev)) {
      std::printf("[gateway_state] %s\n", g->state.c_str());
      // turn winds down when the gateway returns to idle
      if (g->state == "idle") turn_active.store(false);
      else turn_active.store(true);
    } else if (auto* t = std::get_if<TranscriptDelta>(&ev)) {
      std::printf("[you said] %s%s\n", t->text.c_str(), t->is_final ? "" : " …");
    } else if (auto* a = std::get_if<AdoptionEvent>(&ev)) {
      std::printf("[adoption] %s -> %s\n", a->previous.c_str(), a->current.c_str());
    } else if (auto* e = std::get_if<SatError>(&ev)) {
      std::printf("[error] %s\n", e->message.c_str());
    }
  };

  aivg::sat::Satellite sat(std::move(opts));
  std::printf("[connect] %s\n", gw.c_str());
  sat.connect().get();
  for (int i = 0; i < 200 && !sat.isAdopted(); ++i) std::this_thread::sleep_for(50ms);
  if (!sat.isAdopted()) { std::printf("not adopted; run `aivg device adopt %s`\n", dev.c_str()); }

  // Long-lived session; mic gated by wake word (Principle I).
  sat.beginSession().get();
  sat.mute();
  std::printf("[ready] say the wake word…\n");

  // Wake-word control loop.
  while (true) {
    if (wake_hit.exchange(false)) {
      std::printf("[wake] streaming utterance\n");
      sat.unmute();                       // open mic upstream
      turn_active.store(true);
      // Stream until the gateway finishes the turn (gateway_state -> idle),
      // then close the mic again. Cap the turn so a stuck pipeline recovers.
      auto deadline = std::chrono::steady_clock::now() + 90s;
      while (turn_active.load() && std::chrono::steady_clock::now() < deadline)
        std::this_thread::sleep_for(100ms);
      sat.mute();
      std::printf("[idle] waiting for wake word…\n");
    }
    std::this_thread::sleep_for(50ms);
  }
  // (unreached in this demo) sat.endSession().get(); sat.disconnect().get();
  // pw_thread_loop_stop(pa.loop); pw_thread_loop_destroy(pa.loop); pw_deinit();
}
