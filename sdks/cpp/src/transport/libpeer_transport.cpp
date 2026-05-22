// libaivg-sat — libpeer WebRTC transport (feature 020, T015).
#include "transport/libpeer_transport.hpp"

#include <chrono>
#include <cstdio>
#include <cstdlib>
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
  // NOTE: libpeer must be patched so the offerer takes the DTLS *client*
  // role (peer_connection_create_sdp: SDP_TYPE_OFFER -> DTLS_SRTP_ROLE_CLIENT),
  // so it offers a=setup:active and initiates the handshake against aiortc's
  // OpenSSL server. The default (offerer=server) makes mbedTLS-server reject
  // aiortc's ClientHello with handshake_failure. See HANDOFF.md / research.md.
  const char* offer = peer_connection_create_offer(pc_);
  return offer ? std::string(offer) : std::string();
}

namespace {
// libpeer's SDP parser splits strictly on CRLF and only processes lines
// terminated by it (peer_connection.c). Gateways that emit LF-only SDP
// (e.g. aiortc/Python) would otherwise yield an empty remote fingerprint
// -> DTLS-SRTP "no remote fingerprint". Normalize to CRLF + trailing CRLF.
std::string normalize_crlf(const std::string& s) {
  std::string out;
  out.reserve(s.size() + 64);
  for (std::size_t i = 0; i < s.size(); ++i) {
    char c = s[i];
    if (c == '\n' && (i == 0 || s[i - 1] != '\r')) out.push_back('\r');
    out.push_back(c);
  }
  if (out.size() < 2 || out.compare(out.size() - 2, 2, "\r\n") != 0) out.append("\r\n");
  return out;
}

// libpeer's parser keeps the LAST a=fingerprint line and only verifies with
// SHA-256; gateways (aiortc) advertise sha-256/384/512, so the sha-512 line
// would win and break cert verification. Keep only the sha-256 fingerprint.
std::string sanitize_answer(const std::string& crlf_sdp) {
  std::string out;
  out.reserve(crlf_sdp.size());
  std::size_t start = 0;
  while (start < crlf_sdp.size()) {
    std::size_t end = crlf_sdp.find("\r\n", start);
    if (end == std::string::npos) end = crlf_sdp.size();
    std::string line = crlf_sdp.substr(start, end - start);
    bool is_fp = line.rfind("a=fingerprint:", 0) == 0;
    bool is_sha256 = line.rfind("a=fingerprint:sha-256 ", 0) == 0;
    if (!is_fp || is_sha256) {
      out += line;
      out += "\r\n";
    }
    start = end + 2;
  }
  return out;
}
}  // namespace

bool LibpeerTransport::set_answer_and_run(const std::string& answer_sdp) {
  if (pc_ == nullptr || answer_sdp.empty()) return false;
  std::string sdp = sanitize_answer(normalize_crlf(answer_sdp));
  if (std::getenv("AIVG_SAT_DEBUG_SDP")) {
    std::fprintf(stderr, "===ANSWER SDP (%zu bytes, normalized)===\n", sdp.size());
    for (std::size_t i = 0; i < sdp.size(); ++i) {
      char c = sdp[i];
      if (c == '\r') std::fputs("\\r", stderr);
      else if (c == '\n') std::fputs("\\n\n", stderr);
      else std::fputc(c, stderr);
    }
    std::fputs("\n===END ANSWER===\n", stderr);
  }
  peer_connection_set_remote_description(pc_, sdp.c_str(), SDP_TYPE_ANSWER);
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

bool LibpeerTransport::is_completed() const noexcept {
  return pc_ != nullptr && peer_connection_get_state(pc_) == PEER_CONNECTION_COMPLETED;
}

void LibpeerTransport::send_opus(const std::uint8_t* payload, std::size_t bytes) {
  // peer_connection_send_audio() self-guards on PEER_CONNECTION_COMPLETED
  // (returns -1 / drops before the handshake finishes), so it is safe to
  // call as soon as the session begins — no separate connected gate, and
  // no dependency on the ICE-state callback firing (which libpeer may not
  // deliver for COMPLETED even when media is flowing).
  if (pc_ != nullptr && payload != nullptr && bytes > 0) {
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
