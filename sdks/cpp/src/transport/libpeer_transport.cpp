// libaivg-sat — libpeer WebRTC transport (feature 020, T015).
#include "transport/libpeer_transport.hpp"

#include <chrono>
#include <mutex>

extern "C" {
#include <peer.h>
}

namespace aivg::sat::detail {
namespace {

// peer_init() / peer_deinit() are process-global; guard them.
std::mutex g_peer_mu;
int g_peer_refs = 0;

void peer_global_acquire() {
  std::lock_guard<std::mutex> lk(g_peer_mu);
  if (g_peer_refs++ == 0) peer_init();
}
void peer_global_release() {
  std::lock_guard<std::mutex> lk(g_peer_mu);
  if (--g_peer_refs == 0) peer_deinit();
}

// C trampolines: user_data is the LibpeerTransport*.
void on_audio_track_thunk(uint8_t* data, size_t size, void* userdata) {
  static_cast<LibpeerTransport*>(userdata)->handle_remote_opus(data, size);
}
void on_ice_state_thunk(PeerConnectionState state, void* userdata) {
  static_cast<LibpeerTransport*>(userdata)->handle_state(static_cast<int>(state));
}

}  // namespace

LibpeerTransport::LibpeerTransport() { peer_global_acquire(); }

LibpeerTransport::~LibpeerTransport() {
  stop();
  peer_global_release();
}

void LibpeerTransport::handle_remote_opus(const std::uint8_t* data, std::size_t size) {
  if (on_remote_) on_remote_(data, size);
}

void LibpeerTransport::handle_state(int state) {
  if (state == PEER_CONNECTION_COMPLETED || state == PEER_CONNECTION_CONNECTED) {
    if (!connected_.exchange(true) && on_connected_) on_connected_();
  } else if (state == PEER_CONNECTION_FAILED || state == PEER_CONNECTION_CLOSED ||
             state == PEER_CONNECTION_DISCONNECTED) {
    if (connected_.exchange(false) && on_failed_) on_failed_();
  }
}

std::string LibpeerTransport::create_offer() {
  PeerConfiguration config{};
  config.audio_codec = CODEC_OPUS;
  config.video_codec = CODEC_NONE;
  config.datachannel = DATA_CHANNEL_STRING;  // call-scoped UI events (Principle III)
  config.onaudiotrack = on_audio_track_thunk;
  config.user_data = this;

  pc_ = peer_connection_create(&config);
  if (pc_ == nullptr) return {};
  peer_connection_oniceconnectionstatechange(pc_, on_ice_state_thunk);

  // Synchronous: gathers host candidates and returns the full offer SDP.
  const char* offer = peer_connection_create_offer(pc_);
  return offer ? std::string(offer) : std::string();
}

bool LibpeerTransport::set_answer_and_run(const std::string& answer_sdp) {
  if (pc_ == nullptr || answer_sdp.empty()) return false;
  peer_connection_set_remote_description(pc_, answer_sdp.c_str(), SDP_TYPE_ANSWER);
  running_.store(true);
  loop_ = std::thread([this] {
    using namespace std::chrono;
    while (running_.load()) {
      peer_connection_loop(pc_);
      std::this_thread::sleep_for(microseconds(1000));
    }
  });
  return true;
}

void LibpeerTransport::send_opus(const std::uint8_t* payload, std::size_t bytes) {
  if (pc_ != nullptr && connected_.load() && payload != nullptr && bytes > 0) {
    peer_connection_send_audio(pc_, payload, bytes);
  }
}

void LibpeerTransport::stop() {
  if (running_.exchange(false)) {
    if (loop_.joinable()) loop_.join();
  }
  if (pc_ != nullptr) {
    peer_connection_close(pc_);
    peer_connection_destroy(pc_);
    pc_ = nullptr;
  }
  connected_.store(false);
}

}  // namespace aivg::sat::detail
