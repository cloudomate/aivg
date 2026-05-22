// libaivg-sat — live ControlPlane smoke (feature 020, T013 proof).
//
// Runs the full ControlPlane (register + heartbeat loop + dispatch +
// adoption tracking) against a real gateway. Needs a live gateway. Usage:
//   control_plane_smoke ws://<host>:8643/satellite/ws <device_id>
#include <chrono>
#include <cstdio>
#include <string>
#include <thread>

#include "aivg/sat/satellite.hpp"
#include "control_plane.hpp"

using namespace std::chrono_literals;
namespace detail = aivg::sat::detail;

int main(int argc, char** argv) {
  std::string url = argc > 1 ? argv[1] : "ws://127.0.0.1:8643/satellite/ws";
  std::string device_id = argc > 2 ? argv[2] : "cpp-cp-smoke";

  detail::ControlPlane::Callbacks cb;
  cb.on_adoption = [](const std::string& p, const std::string& c) {
    std::printf("[adoption] %s -> %s\n", p.c_str(), c.c_str());
  };
  cb.on_gateway_state = [](const std::string& s, const std::string& sid) {
    std::printf("[gateway_state] %s (session=%s)\n", s.c_str(), sid.c_str());
  };
  cb.on_error = [](const std::string& code, const std::string& d) {
    std::printf("[error] %s: %s\n", code.c_str(), d.c_str());
  };

  aivg::sat::ReconnectPolicy rp;  // defaults: 500ms base, 30s cap, jitter
  detail::ControlPlane cp(url, device_id, "0.1.0", rp, /*heartbeat_ms=*/1000, cb);

  std::printf("[start] %s device=%s\n", url.c_str(), device_id.c_str());
  cp.start();

  // Run ~4s: expect open + adopted + at least a couple of heartbeats.
  for (int i = 0; i < 80 && !(cp.is_adopted() && cp.heartbeats_sent() >= 2); ++i)
    std::this_thread::sleep_for(50ms);

  std::printf("[status] open=%d adopted=%d registers=%u heartbeats=%u\n", cp.is_open(),
              cp.is_adopted(), cp.registers_sent(), cp.heartbeats_sent());
  cp.stop();

  if (cp.is_adopted() && cp.registers_sent() >= 1 && cp.heartbeats_sent() >= 1) {
    std::printf("PASS: control plane registered, adopted, heartbeating\n");
    return 0;
  }
  std::printf("FAIL\n");
  return 1;
}
