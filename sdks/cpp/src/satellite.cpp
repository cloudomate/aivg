// libaivg-sat — Satellite orchestration (feature 020, T019).
//
// Wires the control plane (always-on WS) and the voice session (per-call
// WebRTC) behind the public API. Platform-agnostic: never names a gateway
// implementation or an agent platform.
#include "aivg/sat/satellite.hpp"

#include <atomic>
#include <chrono>
#include <cstdlib>
#include <future>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "control_plane.hpp"
#include "negotiate.hpp"
#include "transport/webrtc_transport.hpp"
#include "voice_session.hpp"
#ifdef AIVG_SAT_HAVE_GRPC
#include "transport/grpc_transport.hpp"
#endif

namespace aivg::sat {
namespace {

constexpr std::uint32_t kDefaultHeartbeatMs = 30000;

bool renegotiate_disabled() {
  // Opt-out for sites that don't want SDK-driven WebRTC renegotiation on
  // gateway-restart reconnects (e.g. lab benches that prefer manual recovery).
  const char* v = std::getenv("AIVG_SAT_DISABLE_WEBRTC_RENEGOTIATE");
  return v != nullptr && v[0] != '\0' && v[0] != '0';
}

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

// Transports this build can speak (best-first). satellite.cpp only compiles
// under the voice plane, so WebRTC is always present; gRPC when compiled in.
std::vector<std::string> build_transport_caps() {
  std::vector<std::string> caps;
#ifdef AIVG_SAT_HAVE_GRPC
  caps.emplace_back("grpc");  // preferred for native
#endif
  caps.emplace_back("webrtc");
  return caps;
}

std::string pref_to_pin(TransportPref p) {
  switch (p) {
    case TransportPref::Webrtc: return "webrtc";
    case TransportPref::Grpc:   return "grpc";
    default:                    return "";  // Auto = negotiate
  }
}

#ifdef AIVG_SAT_HAVE_GRPC
std::string grpc_target(const SatelliteOptions& o) {
  // "host:grpc_port" derived from the gateway_url authority.
  std::string s = o.gateway_url;
  auto scheme = s.find("://");
  if (scheme != std::string::npos) s = s.substr(scheme + 3);
  auto slash = s.find('/');
  if (slash != std::string::npos) s = s.substr(0, slash);
  auto colon = s.rfind(':');
  if (colon != std::string::npos) s = s.substr(0, colon);  // strip the mgmt port
  return s + ":" + std::to_string(o.grpc_port);
}

std::string mint_session_id(const std::string& device_id) {
  auto ns = std::chrono::steady_clock::now().time_since_epoch().count();
  return device_id + "-g" + std::to_string(ns);
}
#endif

// Build the voice-plane transport for this session, honouring the operator pin
// and the gateway's negotiated choice (feature 022 / US3). Returns nullptr and
// sets `err` if the selection is unsatisfiable (e.g. a pin for a transport this
// build doesn't have). Centralised so the initial-session and reconnect paths
// agree.
std::unique_ptr<detail::Transport> make_voice_transport(const SatelliteOptions& o,
                                                        const std::string& chosen,
                                                        std::string& err) {
  auto choice = detail::choose_transport(build_transport_caps(), pref_to_pin(o.transport), chosen);
  if (!choice.ok) {
    err = choice.error;
    return nullptr;
  }
#ifdef AIVG_SAT_HAVE_GRPC
  if (choice.transport == "grpc") {
    detail::GrpcTransportOptions g;
    g.target = grpc_target(o);
    g.session_id = mint_session_id(o.device_id);
    g.use_tls = o.grpc_tls;
    return std::make_unique<detail::GrpcTransport>(std::move(g));
  }
#endif
  return std::make_unique<detail::WebrtcTransport>(derive_voice_base(o), o.device_id);
}

}  // namespace

struct Satellite::Impl {
  explicit Impl(SatelliteOptions o) : opts(std::move(o)) {}

  SatelliteOptions opts;
  std::unique_ptr<detail::ControlPlane> cp;
  std::unique_ptr<detail::VoiceSession> vs;
  std::atomic<SatelliteState> state{SatelliteState::Idle};
  // Guards voice-session lifecycle so a gateway-restart reconnect can't race
  // with a user-initiated beginSession/endSession (bug 5).
  std::mutex vs_mu;

  void emit(const SatEvent& ev) {
    if (opts.on_event) opts.on_event(ev);
  }

  // Feature 022 / T015 — map a voice-transport event onto the public SatEvent
  // surface (FR-006/FR-013). `sid` is captured per-session at begin time.
  void on_transport_event(const detail::TransportEvent& te, const std::string& sid) {
    using K = detail::TransportEvent::Kind;
    switch (te.kind) {
      case K::Transcript:      emit(TranscriptDelta{te.text, te.is_final}); break;
      case K::SpeakingStarted: emit(RemoteStreamEvent{"speaking_started"}); break;
      case K::SpeakingEnded:   emit(RemoteStreamEvent{"speaking_ended"}); break;
      case K::VadDetected:     emit(RemoteStreamEvent{"vad_detected"}); break;
      case K::StreamDropped:
        emit(VoiceSessionResult{sid, te.reason.empty() ? "dropped" : te.reason});
        break;
    }
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
  // Bug 5 — gateway restart kills the WebRTC PeerConnection even though the
  // management WS auto-reconnects. Rebuild the voice session against the
  // restarted gateway so subsequent wake-word hits can stream again without a
  // client process restart.
  cb.on_reconnected = [this]() {
    if (renegotiate_disabled()) return;
    std::lock_guard<std::mutex> lk(impl_->vs_mu);
    if (!impl_->vs) return;  // no active session — nothing to renegotiate
    std::string prev_sid = impl_->vs->session_id();
    impl_->vs->end();
    impl_->vs.reset();
    impl_->emit(VoiceSessionResult{prev_sid, "gateway_reconnected"});

    std::string terr;
    auto transport = make_voice_transport(
        impl_->opts, impl_->cp ? impl_->cp->chosen_transport() : std::string{}, terr);
    if (!transport) {
      impl_->emit(SatError{SatErrorCode::SignalingFailed, terr, std::nullopt});
      return;
    }
    auto fresh = std::make_unique<detail::VoiceSession>(
        std::move(transport), impl_->opts.audio_input, impl_->opts.audio_output);
    if (!fresh->begin()) {
      impl_->emit(SatError{SatErrorCode::SignalingFailed,
                           "voice renegotiate after gateway reconnect failed", std::nullopt});
      return;
    }
    {
      const std::string sid = fresh->session_id();
      auto* ip = impl_.get();
      fresh->set_on_event(
          [ip, sid](const detail::TransportEvent& te) { ip->on_transport_event(te, sid); });
    }
    fresh->unmute();
    impl_->state.store(SatelliteState::Listening);
    impl_->emit(VoiceSession{fresh->session_id()});
    impl_->vs = std::move(fresh);
  };

  impl_->cp = std::make_unique<detail::ControlPlane>(
      control_ws_url(impl_->opts.gateway_url), impl_->opts.device_id,
      impl_->opts.firmware_version, impl_->opts.reconnect, kDefaultHeartbeatMs, std::move(cb),
      build_transport_caps());
  impl_->cp->start();

  std::promise<void> p;
  p.set_value();
  return p.get_future();
}

std::future<void> Satellite::disconnect() {
  {
    std::lock_guard<std::mutex> lk(impl_->vs_mu);
    if (impl_->vs) impl_->vs->end();
    impl_->vs.reset();
  }
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
  std::lock_guard<std::mutex> lk(impl_->vs_mu);
  std::string terr;
  auto transport = make_voice_transport(
      impl_->opts, impl_->cp ? impl_->cp->chosen_transport() : std::string{}, terr);
  if (!transport) {
    impl_->emit(SatError{SatErrorCode::SignalingFailed, terr, std::nullopt});
    p.set_value();
    return p.get_future();
  }
  impl_->vs = std::make_unique<detail::VoiceSession>(
      std::move(transport), impl_->opts.audio_input, impl_->opts.audio_output);
  if (impl_->vs->begin()) {
    const std::string sid = impl_->vs->session_id();
    auto* ip = impl_.get();
    impl_->vs->set_on_event(
        [ip, sid](const detail::TransportEvent& te) { ip->on_transport_event(te, sid); });
    impl_->vs->unmute();
    impl_->state.store(SatelliteState::Listening);
    impl_->emit(VoiceSession{sid});
  } else {
    impl_->emit(SatError{SatErrorCode::SignalingFailed, "beginSession failed", std::nullopt});
  }
  p.set_value();
  return p.get_future();
}

std::future<void> Satellite::endSession() {
  std::lock_guard<std::mutex> lk(impl_->vs_mu);
  if (impl_->vs) {
    impl_->emit(VoiceSessionResult{impl_->vs->session_id(), "ended"});
    impl_->vs->end();
    impl_->vs.reset();
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
