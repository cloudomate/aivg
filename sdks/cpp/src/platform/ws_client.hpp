// libaivg-sat — control-plane WebSocket abstraction (feature 020, internal).
//
// Constitution Principle III: the control plane is a SEPARATE, always-on
// connection from the WebRTC voice plane and must stay up with no active
// call. libpeer covers the voice plane only; this interface abstracts the
// durable control WS so the two tiers can supply different transports:
//   - POSIX:    ws_client_posix.cpp   (over mbedTLS)        [task T012]
//   - ESP32-S3: ws_client_espidf.cpp  (esp_websocket_client) [task T022]
#ifndef AIVG_SAT_PLATFORM_WS_CLIENT_HPP
#define AIVG_SAT_PLATFORM_WS_CLIENT_HPP

#include <functional>
#include <memory>
#include <string>

namespace aivg::sat::detail {

class WsClient {
 public:
  using OnMessage = std::function<void(const std::string& text)>;
  using OnOpen = std::function<void()>;
  using OnClose = std::function<void(int code, const std::string& reason)>;

  virtual ~WsClient() = default;

  virtual void connect(const std::string& url) = 0;
  virtual void send(const std::string& text) = 0;
  virtual void close() = 0;

  virtual void set_on_message(OnMessage cb) = 0;
  virtual void set_on_open(OnOpen cb) = 0;
  virtual void set_on_close(OnClose cb) = 0;
};

// Factory implemented per tier (one definition linked per build profile).
std::unique_ptr<WsClient> make_ws_client();

}  // namespace aivg::sat::detail

#endif  // AIVG_SAT_PLATFORM_WS_CLIENT_HPP
