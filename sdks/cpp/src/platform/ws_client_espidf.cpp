// libaivg-sat — ESP32-S3 control-plane WebSocket client (feature 020, T022;
// completed by aivg-devices feature 005).
//
// Implements the WsClient interface over Espressif's `esp_websocket_client`
// (managed component `espressif/esp_websocket_client`). This is the ESP tier's
// `make_ws_client()`; the IDF component build links THIS file and excludes
// `ws_client_posix.cpp` (one factory definition per build profile —
// ws_client.hpp). Guarded by ESP_PLATFORM so it is inert in a POSIX build.
#ifdef ESP_PLATFORM

#include <atomic>
#include <string>

#include "esp_websocket_client.h"

#include "platform/ws_client.hpp"

namespace aivg::sat::detail {
namespace {

class EspWsClient : public WsClient {
 public:
  ~EspWsClient() override { close(); }

  void connect(const std::string& url) override {
    if (client_) return;
    esp_websocket_client_config_t cfg = {};
    cfg.uri = url.c_str();
    // Keep the control plane alive with no active call (Principle III).
    cfg.reconnect_timeout_ms = 2000;
    cfg.network_timeout_ms = 10000;
    client_ = esp_websocket_client_init(&cfg);
    if (!client_) return;
    esp_websocket_register_events(client_, WEBSOCKET_EVENT_ANY, &EspWsClient::event_thunk, this);
    esp_websocket_client_start(client_);
  }

  void send(const std::string& text) override {
    if (!client_) return;
    esp_websocket_client_send_text(client_, text.c_str(), static_cast<int>(text.size()),
                                   portMAX_DELAY);
  }

  void close() override {
    if (!client_) return;
    esp_websocket_client_stop(client_);
    esp_websocket_client_destroy(client_);
    client_ = nullptr;
  }

  void set_on_message(OnMessage cb) override { on_message_ = std::move(cb); }
  void set_on_open(OnOpen cb) override { on_open_ = std::move(cb); }
  void set_on_close(OnClose cb) override { on_close_ = std::move(cb); }

 private:
  static void event_thunk(void* arg, esp_event_base_t, int32_t id, void* data) {
    static_cast<EspWsClient*>(arg)->on_event(id, static_cast<esp_websocket_event_data_t*>(data));
  }

  void on_event(int32_t id, esp_websocket_event_data_t* ev) {
    switch (id) {
      case WEBSOCKET_EVENT_CONNECTED:
        if (on_open_) on_open_();
        break;
      case WEBSOCKET_EVENT_DATA:
        // Text frames (op 0x01) only; control frames / pings ignored. Reassemble
        // fragmented payloads via payload_offset/payload_len.
        if (ev && ev->op_code == 0x01 && ev->data_ptr && ev->data_len > 0) {
          if (ev->payload_offset == 0) rx_.clear();
          rx_.append(ev->data_ptr, ev->data_len);
          if (ev->payload_offset + ev->data_len >= ev->payload_len && on_message_) {
            on_message_(rx_);
            rx_.clear();
          }
        }
        break;
      case WEBSOCKET_EVENT_DISCONNECTED:
      case WEBSOCKET_EVENT_CLOSED:
        if (on_close_) on_close_(1006, "ws closed");
        break;
      default:
        break;
    }
  }

  esp_websocket_client_handle_t client_ = nullptr;
  OnMessage on_message_;
  OnOpen on_open_;
  OnClose on_close_;
  std::string rx_;
};

}  // namespace

std::unique_ptr<WsClient> make_ws_client() { return std::make_unique<EspWsClient>(); }

}  // namespace aivg::sat::detail

#endif  // ESP_PLATFORM
