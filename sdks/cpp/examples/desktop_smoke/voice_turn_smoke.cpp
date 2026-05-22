// libaivg-sat — WAV-in/WAV-out voice-turn smoke (feature 020, T020).
//
// Drives ONE push-to-talk voice turn against a live gateway using only the
// public Satellite API: read prompt.wav -> beginSession -> stream the WAV as
// mic audio -> collect reply audio -> write reply.wav. Exit 0 iff reply is
// non-empty. PCM16 mono @ 48 kHz both ways.
//
// Usage:
//   voice_turn_smoke <ws://host:8643> <http://host:8644> <device_id> <in.wav> <out.wav>
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <mutex>
#include <string>
#include <thread>
#include <variant>
#include <vector>

#include "aivg/sat/satellite.hpp"

using namespace std::chrono_literals;

namespace {

// Minimal canonical PCM16-mono WAV reader (assumes 48 kHz mono 16-bit).
std::vector<std::int16_t> read_wav(const std::string& path) {
  std::vector<std::int16_t> pcm;
  std::ifstream f(path, std::ios::binary);
  if (!f) return pcm;
  char hdr[44];
  f.read(hdr, 44);
  if (f.gcount() < 44 || std::strncmp(hdr, "RIFF", 4) != 0) return pcm;
  // Walk to the 'data' chunk (header may have extra chunks; simple path here).
  std::vector<char> rest((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
  pcm.resize(rest.size() / 2);
  std::memcpy(pcm.data(), rest.data(), pcm.size() * 2);
  return pcm;
}

void write_wav(const std::string& path, const std::vector<std::int16_t>& pcm, int rate) {
  std::ofstream f(path, std::ios::binary);
  std::uint32_t data_bytes = static_cast<std::uint32_t>(pcm.size() * 2);
  std::uint32_t chunk = 36 + data_bytes;
  std::uint16_t ch = 1, bits = 16, fmt = 1;
  std::uint32_t byte_rate = rate * ch * bits / 8;
  std::uint16_t block = ch * bits / 8;
  auto w = [&](const void* p, size_t n) { f.write(static_cast<const char*>(p), n); };
  f.write("RIFF", 4); w(&chunk, 4); f.write("WAVE", 4);
  f.write("fmt ", 4); std::uint32_t sub1 = 16; w(&sub1, 4); w(&fmt, 2); w(&ch, 2);
  w(&rate, 4); w(&byte_rate, 4); w(&block, 2); w(&bits, 2);
  f.write("data", 4); w(&data_bytes, 4);
  f.write(reinterpret_cast<const char*>(pcm.data()), data_bytes);
}

}  // namespace

int main(int argc, char** argv) {
  if (argc < 6) {
    std::printf("usage: %s <ws://h:8643> <http://h:8644> <device_id> <in.wav> <out.wav>\n", argv[0]);
    return 2;
  }
  std::string gw = argv[1], sig = argv[2], dev = argv[3], in_path = argv[4], out_path = argv[5];

  auto prompt = read_wav(in_path);
  if (prompt.empty()) {
    std::printf("FAIL: could not read %s\n", in_path.c_str());
    return 2;
  }
  std::printf("[in] %s: %zu samples (%.2fs @48k)\n", in_path.c_str(), prompt.size(),
              prompt.size() / 48000.0);

  std::atomic<std::size_t> read_pos{0};
  std::vector<std::int16_t> reply;
  std::mutex reply_mu;
  std::atomic<bool> got_reply{false};

  aivg::sat::SatelliteOptions opts;
  opts.gateway_url = gw;
  opts.signaling_url = sig;
  opts.device_id = dev;
  opts.device_name = "cpp-voice-smoke";
  opts.device_type = "linux";
  opts.firmware_version = "0.1.0";
  // Mic: feed the WAV out in 20 ms frames, then silence (return 0 -> end).
  opts.audio_input = [&](std::int16_t* buf, std::size_t frames) -> std::size_t {
    std::size_t pos = read_pos.load();
    if (pos >= prompt.size()) return 0;
    std::size_t n = std::min(frames, prompt.size() - pos);
    std::memcpy(buf, prompt.data() + pos, n * 2);
    read_pos.store(pos + n);
    return n;
  };
  // Speaker: collect reply audio.
  opts.audio_output = [&](const std::int16_t* buf, std::size_t frames) {
    std::lock_guard<std::mutex> lk(reply_mu);
    reply.insert(reply.end(), buf, buf + frames);
    got_reply.store(true);
  };
  opts.on_event = [&](const aivg::sat::SatEvent& ev) {
    if (auto* t = std::get_if<aivg::sat::TranscriptDelta>(&ev))
      std::printf("[transcript] %s%s\n", t->text.c_str(), t->is_final ? " (final)" : "");
    else if (auto* g = std::get_if<aivg::sat::GatewayStatePayload>(&ev))
      std::printf("[gateway_state] %s\n", g->state.c_str());
    else if (auto* e = std::get_if<aivg::sat::SatError>(&ev))
      std::printf("[error] %s\n", e->message.c_str());
  };

  aivg::sat::Satellite sat(std::move(opts));
  std::printf("[connect] %s\n", gw.c_str());
  sat.connect().get();

  for (int i = 0; i < 100 && !sat.isAdopted(); ++i) std::this_thread::sleep_for(50ms);
  std::printf("[adopted] %d\n", sat.isAdopted());

  std::printf("[beginSession]\n");
  sat.beginSession().get();

  // Wait for the turn: reply audio to start, then settle (no new audio for 1.5s).
  auto deadline = std::chrono::steady_clock::now() + 30s;
  std::size_t last = 0;
  auto last_grow = std::chrono::steady_clock::now();
  while (std::chrono::steady_clock::now() < deadline) {
    std::this_thread::sleep_for(200ms);
    std::size_t cur;
    { std::lock_guard<std::mutex> lk(reply_mu); cur = reply.size(); }
    if (cur != last) { last = cur; last_grow = std::chrono::steady_clock::now(); }
    else if (got_reply.load() &&
             std::chrono::steady_clock::now() - last_grow > 1500ms) break;
  }

  sat.endSession().get();
  sat.disconnect().get();

  std::vector<std::int16_t> final_reply;
  { std::lock_guard<std::mutex> lk(reply_mu); final_reply = reply; }
  if (!final_reply.empty()) {
    write_wav(out_path, final_reply, 48000);
    std::printf("PASS: reply %zu samples (%.2fs) -> %s\n", final_reply.size(),
                final_reply.size() / 48000.0, out_path.c_str());
    return 0;
  }
  std::printf("FAIL: no reply audio received\n");
  return 1;
}
