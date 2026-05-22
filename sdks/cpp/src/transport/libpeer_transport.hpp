// libaivg-sat — libpeer WebRTC transport (feature 020, T015, internal).
//
// Wraps libpeer's C PeerConnection: Opus audio codec, full ICE
// gather-then-offer (create_offer is synchronous), DTLS-SRTP. The voice
// session drives it: create_offer -> POST to gateway -> set_answer ->
// pump loop -> on COMPLETED, media flows. Remote Opus payloads arrive via
// the onaudiotrack callback; outbound Opus goes through send_opus.
#ifndef AIVG_SAT_TRANSPORT_LIBPEER_TRANSPORT_HPP
#define AIVG_SAT_TRANSPORT_LIBPEER_TRANSPORT_HPP

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <string>
#include <thread>

struct PeerConnection;

namespace aivg::sat::detail {

class LibpeerTransport {
 public:
  using OnRemoteOpus = std::function<void(const std::uint8_t* data, std::size_t size)>;
  using OnConnected = std::function<void()>;
  using OnFailed = std::function<void()>;

  LibpeerTransport();
  ~LibpeerTransport();

  LibpeerTransport(const LibpeerTransport&) = delete;
  LibpeerTransport& operator=(const LibpeerTransport&) = delete;

  void set_on_remote_opus(OnRemoteOpus cb) { on_remote_ = std::move(cb); }
  void set_on_connected(OnConnected cb) { on_connected_ = std::move(cb); }
  void set_on_failed(OnFailed cb) { on_failed_ = std::move(cb); }

  // Create the PeerConnection + Opus offer (synchronous, includes host
  // candidates). Returns the offer SDP, or empty on failure.
  std::string create_offer();

  // Apply the gateway's answer SDP and start pumping the connection.
  bool set_answer_and_run(const std::string& answer_sdp);

  // Send one Opus payload (already encoded) to the remote.
  void send_opus(const std::uint8_t* payload, std::size_t bytes);

  bool connected() const noexcept { return connected_.load(); }
  // True once libpeer's PeerConnection reaches COMPLETED (DTLS-SRTP up).
  // Read directly from libpeer rather than relying on the state callback,
  // which libpeer may not deliver. peer_connection_send_audio only sends
  // in this state, so the mic pump must gate on it.
  bool is_completed() const noexcept;
  void stop();

  // C-callback trampolines (public so the static thunks can reach them).
  void handle_remote_opus(const std::uint8_t* data, std::size_t size);
  void handle_state(int state);

 private:
  PeerConnection* pc_ = nullptr;
  std::thread loop_;
  std::atomic<bool> running_{false};
  std::atomic<bool> connected_{false};
  OnRemoteOpus on_remote_;
  OnConnected on_connected_;
  OnFailed on_failed_;
};

}  // namespace aivg::sat::detail

#endif  // AIVG_SAT_TRANSPORT_LIBPEER_TRANSPORT_HPP
