// libaivg-sat — control-plane manager (feature 020, T013, internal).
//
// Owns the always-on control WS (Principle III): registers on open, runs a
// heartbeat loop, dispatches inbound frames, tracks adoption, and
// auto-reconnects with backoff (FR-015). Built on the proven WsClient +
// proto layer. The consumer only ever sees high-level callbacks.
#ifndef AIVG_SAT_CONTROL_PLANE_HPP
#define AIVG_SAT_CONTROL_PLANE_HPP

#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <thread>

#include "aivg/sat/satellite.hpp"
#include "platform/ws_client.hpp"

namespace aivg::sat::detail {

class ControlPlane {
 public:
  struct Callbacks {
    std::function<void(const std::string& prev, const std::string& cur)> on_adoption;
    std::function<void(const std::string& gw_state, const std::string& session_id)>
        on_gateway_state;
    std::function<void(const std::string& verb, const std::string& request_id)> on_command;
    std::function<void(const std::string& raw)> on_log;
    std::function<void(const std::string& code, const std::string& detail)> on_error;
    // Fires when the control WS reopens after a non-clean disconnect (i.e. not
    // the initial connect). Lets the caller renegotiate the voice plane, which
    // does not survive a gateway restart even though the management plane
    // auto-reconnects. See spec FR-015 / upstream bug 5.
    std::function<void()> on_reconnected;
  };

  ControlPlane(std::string gateway_ws_url, std::string device_id, std::string firmware_version,
               ReconnectPolicy reconnect, std::uint32_t heartbeat_interval_ms, Callbacks cb);
  ~ControlPlane();

  void start();  // connect + register + heartbeat loop + auto-reconnect
  void stop();
  bool is_adopted() const noexcept { return adopted_.load(); }
  bool is_open() const noexcept { return open_.load(); }

  // Test/diagnostic counters.
  std::uint32_t heartbeats_sent() const noexcept { return heartbeats_sent_.load(); }
  std::uint32_t registers_sent() const noexcept { return registers_sent_.load(); }

 private:
  void connect_once();
  void on_ws_message(const std::string& text);
  void on_ws_open();
  void on_ws_close(int code, const std::string& reason);
  void heartbeat_loop();

  std::string url_;
  std::string device_id_;
  std::string firmware_version_;
  ReconnectPolicy reconnect_;
  std::uint32_t heartbeat_interval_ms_;
  Callbacks cb_;

  std::unique_ptr<WsClient> ws_;
  std::thread hb_thread_;
  std::thread supervisor_;
  std::mutex mu_;
  std::condition_variable cv_;
  std::atomic<bool> running_{false};
  std::atomic<bool> open_{false};
  std::atomic<bool> adopted_{false};
  // True once we've seen a close after at least one successful open — used to
  // distinguish "first connect" from "reconnect" in on_ws_open. Without this we
  // would fire on_reconnected on the initial handshake too.
  std::atomic<bool> had_disconnect_{false};
  std::atomic<std::uint32_t> attempt_{0};
  std::atomic<std::uint32_t> heartbeats_sent_{0};
  std::atomic<std::uint32_t> registers_sent_{0};
  std::string adoption_state_{"pending"};
};

}  // namespace aivg::sat::detail

#endif  // AIVG_SAT_CONTROL_PLANE_HPP
