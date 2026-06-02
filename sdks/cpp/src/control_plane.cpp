// libaivg-sat — control-plane manager (feature 020, T013).
#include "control_plane.hpp"

#include <chrono>
#include <random>
#include <utility>

#include "aivg/sat/version.hpp"
#include "proto/messages.hpp"
#include "reconnect.hpp"

namespace aivg::sat::detail {

ControlPlane::ControlPlane(std::string gateway_ws_url, std::string device_id,
                           std::string firmware_version, ReconnectPolicy reconnect,
                           std::uint32_t heartbeat_interval_ms, Callbacks cb,
                           std::vector<std::string> transport_capabilities)
    : url_(std::move(gateway_ws_url)),
      device_id_(std::move(device_id)),
      firmware_version_(std::move(firmware_version)),
      reconnect_(reconnect),
      heartbeat_interval_ms_(heartbeat_interval_ms),
      cb_(std::move(cb)),
      transport_capabilities_(std::move(transport_capabilities)) {}

ControlPlane::~ControlPlane() { stop(); }

std::string ControlPlane::chosen_transport() const {
  std::lock_guard<std::mutex> lk(ct_mu_);
  return chosen_transport_;
}

void ControlPlane::start() {
  if (running_.exchange(true)) return;
  hb_thread_ = std::thread([this] { heartbeat_loop(); });
  supervisor_ = std::thread([this] {
    std::mt19937 rng(std::random_device{}());
    std::uniform_real_distribution<double> unit(0.0, 1.0);
    while (running_.load()) {
      connect_once();  // blocks until the connection closes
      if (!running_.load()) break;
      // Reconnect with backoff (FR-015).
      std::uint32_t a = attempt_.fetch_add(1);
      auto delay = next_backoff_ms(reconnect_, a, unit(rng));
      std::unique_lock<std::mutex> lk(mu_);
      cv_.wait_for(lk, std::chrono::milliseconds(delay), [this] { return !running_.load(); });
    }
  });
}

void ControlPlane::stop() {
  if (!running_.exchange(false)) return;
  cv_.notify_all();
  if (ws_) ws_->close();
  if (hb_thread_.joinable()) hb_thread_.join();
  if (supervisor_.joinable()) supervisor_.join();
}

void ControlPlane::connect_once() {
  std::string full = url_ + "?device_id=" + device_id_;
  ws_ = make_ws_client();
  std::atomic<bool> closed{false};
  ws_->set_on_open([this] { on_ws_open(); });
  ws_->set_on_message([this](const std::string& t) { on_ws_message(t); });
  ws_->set_on_close([this, &closed](int code, const std::string& reason) {
    on_ws_close(code, reason);
    closed.store(true);
    cv_.notify_all();
  });
  ws_->connect(full);
  // Block until this connection closes or we're told to stop.
  std::unique_lock<std::mutex> lk(mu_);
  cv_.wait(lk, [&] { return closed.load() || !running_.load(); });
  open_.store(false);
}

void ControlPlane::on_ws_open() {
  const bool was_disconnected = had_disconnect_.exchange(false);
  open_.store(true);
  attempt_.store(0);
  ws_->send(proto::build_register(device_id_, kContractVersion, transport_capabilities_));
  registers_sent_.fetch_add(1);
  // Fire AFTER the re-register so the consumer sees a registered socket.
  if (was_disconnected && cb_.on_reconnected) cb_.on_reconnected();
}

void ControlPlane::on_ws_close(int code, const std::string& reason) {
  open_.store(false);
  // Flag the disconnect so the next on_ws_open knows it's a reconnect. Clean
  // shutdowns (code 1000 from stop()) still flag here; the supervisor stops
  // looping in that case, so no on_reconnected ever fires.
  had_disconnect_.store(true);
  if (cb_.on_error) cb_.on_error("ws_disconnected", reason + " (" + std::to_string(code) + ")");
}

void ControlPlane::on_ws_message(const std::string& text) {
  auto in = proto::parse_inbound(text);
  switch (in.type) {
    case proto::InboundType::Registered: {
      if (!in.chosen_transport.empty()) {
        std::lock_guard<std::mutex> lk(ct_mu_);
        chosen_transport_ = in.chosen_transport;
      }
      if (!in.adoption_state.empty() && in.adoption_state != adoption_state_) {
        std::string prev = adoption_state_;
        adoption_state_ = in.adoption_state;
        adopted_.store(adoption_state_ == "adopted");
        if (cb_.on_adoption) cb_.on_adoption(prev, adoption_state_);
      }
      break;
    }
    case proto::InboundType::StateUpdate: {
      if (in.device_id == device_id_ && !in.adoption_state.empty() &&
          in.adoption_state != adoption_state_) {
        std::string prev = adoption_state_;
        adoption_state_ = in.adoption_state;
        adopted_.store(adoption_state_ == "adopted");
        if (cb_.on_adoption) cb_.on_adoption(prev, adoption_state_);
      }
      break;
    }
    case proto::InboundType::GatewayState:
      if (cb_.on_gateway_state) cb_.on_gateway_state(in.gateway_state, in.session_id);
      break;
    case proto::InboundType::Command:
      if (cb_.on_command) cb_.on_command(in.verb, in.request_id);
      break;
    case proto::InboundType::LogEntry:
      if (cb_.on_log) cb_.on_log(in.raw);
      break;
    case proto::InboundType::Unknown:
      if (cb_.on_error) cb_.on_error("protocol_mismatch", in.raw.substr(0, 64));
      break;
    default:
      break;  // config_changed / ota / agent_event / transcript handled by higher layers
  }
}

void ControlPlane::heartbeat_loop() {
  while (running_.load()) {
    {
      std::unique_lock<std::mutex> lk(mu_);
      cv_.wait_for(lk, std::chrono::milliseconds(heartbeat_interval_ms_),
                   [this] { return !running_.load(); });
    }
    if (!running_.load()) break;
    if (open_.load() && ws_) {
      ws_->send(proto::build_heartbeat(device_id_, SatelliteState::Idle, 0, firmware_version_));
      heartbeats_sent_.fetch_add(1);
    }
  }
}

}  // namespace aivg::sat::detail
