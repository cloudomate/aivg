// libaivg-sat — Satellite orchestration (feature 020, T019).
//
// Wires the control plane (always-on WS) and the voice session (per-call
// WebRTC) behind the public API. Platform-agnostic: never names a gateway
// implementation or an agent platform.
#include "aivg/sat/satellite.hpp"

#include <atomic>
#include <future>
#include <memory>
#include <optional>
#include <string>
#include <utility>

#include "control_plane.hpp"
#include "voice_session.hpp"

namespace aivg::sat {
namespace {

constexpr std::uint32_t kDefaultHeartbeatMs = 30000;

std::string control_ws_url(const std::string& gateway_url) {
  // gateway_url is the management base, e.g. "ws://host:8643".
  if (gateway_url.find("/satellite/ws") != std::string::npos) return gateway_url;
  return gateway_url + "/satellite/ws";
}

std::string derive_voice_base(const SatelliteOptions& o) {
  if (o.signaling_url && !o.signaling_url->empty()) return *o.signaling_url;
  // Best-effort derivation from the management URL: ws->http, :8643->:8644.
  std::string s = o.gateway_url;
  auto repl = [&](const std::string& from, const std::string& to) {
    auto p = s.find(from);
    if (p != std::string::npos) s.replace(p, from.size(), to);
  };
  repl("wss://", "https://");
  repl("ws://", "http://");
  repl(":8643", ":8644");
  // Strip any path (voice base is scheme://authority).
  auto scheme = s.find("://");
  if (scheme != std::string::npos) {
    auto slash = s.find('/', scheme + 3);
    if (slash != std::string::npos) s = s.substr(0, slash);
  }
  return s;
}

}  // namespace

struct Satellite::Impl {
  explicit Impl(SatelliteOptions o) : opts(std::move(o)) {}

  SatelliteOptions opts;
  std::unique_ptr<detail::ControlPlane> cp;
  std::unique_ptr<detail::VoiceSession> vs;
  std::atomic<SatelliteState> state{SatelliteState::Idle};

  void emit(const SatEvent& ev) {
    if (opts.on_event) opts.on_event(ev);
  }
};

Satellite::Satellite(SatelliteOptions options) : impl_(std::make_unique<Impl>(std::move(options))) {}
Satellite::~Satellite() = default;
Satellite::Satellite(Satellite&&) noexcept = default;
Satellite& Satellite::operator=(Satellite&&) noexcept = default;

std::future<void> Satellite::connect() {
  detail::ControlPlane::Callbacks cb;
  cb.on_adoption = [this](const std::string& prev, const std::string& cur) {
    impl_->emit(AdoptionEvent{prev, cur});
  };
  cb.on_gateway_state = [this](const std::string& s, const std::string& sid) {
    impl_->emit(GatewayStatePayload{s, sid.empty() ? std::optional<std::string>{} : sid});
  };
  cb.on_error = [this](const std::string& code, const std::string& detail) {
    impl_->emit(SatError{SatErrorCode::WsDisconnected, code + ": " + detail, std::nullopt});
  };

  impl_->cp = std::make_unique<detail::ControlPlane>(
      control_ws_url(impl_->opts.gateway_url), impl_->opts.device_id,
      impl_->opts.firmware_version, impl_->opts.reconnect, kDefaultHeartbeatMs, std::move(cb));
  impl_->cp->start();

  std::promise<void> p;
  p.set_value();
  return p.get_future();
}

std::future<void> Satellite::disconnect() {
  if (impl_->vs) impl_->vs->end();
  if (impl_->cp) impl_->cp->stop();
  impl_->state.store(SatelliteState::Idle);
  std::promise<void> p;
  p.set_value();
  return p.get_future();
}

std::future<void> Satellite::beginSession() {
  std::promise<void> p;
  if (impl_->cp && !impl_->cp->is_adopted()) {
    impl_->emit(SatError{SatErrorCode::NotAdopted, "device not adopted", std::nullopt});
    p.set_value();
    return p.get_future();
  }
  impl_->vs = std::make_unique<detail::VoiceSession>(derive_voice_base(impl_->opts),
                                                     impl_->opts.device_id, impl_->opts.audio_input,
                                                     impl_->opts.audio_output);
  if (impl_->vs->begin()) {
    impl_->vs->unmute();
    impl_->state.store(SatelliteState::Listening);
    impl_->emit(VoiceSession{impl_->vs->session_id()});
  } else {
    impl_->emit(SatError{SatErrorCode::SignalingFailed, "beginSession failed", std::nullopt});
  }
  p.set_value();
  return p.get_future();
}

std::future<void> Satellite::endSession() {
  if (impl_->vs) {
    impl_->emit(VoiceSessionResult{impl_->vs->session_id(), "ended"});
    impl_->vs->end();
  }
  impl_->state.store(SatelliteState::Idle);
  std::promise<void> p;
  p.set_value();
  return p.get_future();
}

void Satellite::mute() {
  if (impl_->vs) impl_->vs->mute();
}

void Satellite::unmute() {
  if (impl_->vs) impl_->vs->unmute();
}

SatelliteState Satellite::state() const noexcept { return impl_->state.load(); }

bool Satellite::isAdopted() const noexcept { return impl_->cp && impl_->cp->is_adopted(); }

bool Satellite::isMicLive() const noexcept { return impl_->vs && impl_->vs->is_mic_live(); }

}  // namespace aivg::sat
