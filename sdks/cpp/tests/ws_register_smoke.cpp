// libaivg-sat — live control-plane smoke (feature 020, T012/T013 proof).
//
// Connects to a real gateway's control WS, sends `register`, prints inbound
// frames, sends a `heartbeat`, and exits 0 iff a `registered` frame arrived.
// NOT a ctest unit test — needs a live gateway. Usage:
//   ws_register_smoke ws://<host>:8643/satellite/ws <device_id>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <string>
#include <thread>

#include "aivg/sat/state.hpp"
#include "aivg/sat/version.hpp"
#include "platform/ws_client.hpp"
#include "proto/messages.hpp"

namespace proto = aivg::sat::proto;
using namespace std::chrono_literals;

int main(int argc, char** argv) {
  std::string base = argc > 1 ? argv[1] : "ws://127.0.0.1:8643/satellite/ws";
  std::string device_id = argc > 2 ? argv[2] : "cpp-smoke-1";
  std::string url = base + "?device_id=" + device_id;

  auto ws = aivg::sat::detail::make_ws_client();
  std::atomic<bool> registered{false};
  std::atomic<bool> open{false};

  ws->set_on_open([&] {
    open.store(true);
    std::printf("[open] sending register\n");
    ws->send(proto::build_register(device_id, aivg::sat::kContractVersion));
  });
  ws->set_on_message([&](const std::string& text) {
    auto in = proto::parse_inbound(text);
    std::printf("[recv] type=%s %s\n", proto::inbound_type_name(in.type),
                in.adoption_state.empty() ? "" : ("adoption=" + in.adoption_state).c_str());
    if (in.type == proto::InboundType::Registered) registered.store(true);
  });
  ws->set_on_close([&](int code, const std::string& reason) {
    std::printf("[close] code=%d reason=%s\n", code, reason.c_str());
  });

  std::printf("[connect] %s\n", url.c_str());
  ws->connect(url);

  for (int i = 0; i < 50 && !open.load(); ++i) std::this_thread::sleep_for(50ms);
  if (!open.load()) {
    std::printf("FAIL: never opened\n");
    return 2;
  }

  std::this_thread::sleep_for(1s);
  ws->send(proto::build_heartbeat(device_id, aivg::sat::SatelliteState::Idle, 1, "0.1.0"));
  std::printf("[send] heartbeat\n");

  for (int i = 0; i < 60 && !registered.load(); ++i) std::this_thread::sleep_for(50ms);
  ws->close();

  if (registered.load()) {
    std::printf("PASS: registered against gateway\n");
    return 0;
  }
  std::printf("FAIL: no 'registered' frame received\n");
  return 1;
}
