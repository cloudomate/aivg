// libaivg-sat — proto round-trip + classification test (feature 020).
// Verifies the C++ control-plane (de)serialization matches the contract-0.2.0
// shapes in sdks/typescript/src/proto/ws-messages.ts.
#include <cassert>
#include <cstdio>
#include <string>

#include <nlohmann/json.hpp>

#include "aivg/sat/state.hpp"
#include "aivg/sat/version.hpp"
#include "proto/messages.hpp"

namespace proto = aivg::sat::proto;
using aivg::sat::SatelliteState;
using nlohmann::json;

int main() {
  // --- Outbound: register ---
  {
    auto s = proto::build_register("dev-1", aivg::sat::kContractVersion);
    auto j = json::parse(s);
    assert(j.at("type") == "register");
    assert(j.at("device_id") == "dev-1");
    assert(j.at("contract_version") == "0.2.0");
  }

  // --- Outbound: heartbeat ---
  {
    auto s = proto::build_heartbeat("dev-1", SatelliteState::Listening, 42, "0.1.0");
    auto j = json::parse(s);
    assert(j.at("type") == "heartbeat");
    assert(j.at("device_id") == "dev-1");
    assert(j.at("state") == "listening");
    assert(j.at("uptime_s") == 42);
    assert(j.at("firmware_version") == "0.1.0");
  }

  // --- Outbound: command_result (message omitted when empty) ---
  {
    auto j = json::parse(proto::build_command_result("req-9", true));
    assert(j.at("type") == "command_result");
    assert(j.at("request_id") == "req-9");
    assert(j.at("ok") == true);
    assert(!j.contains("message"));
  }

  // --- Inbound: registered (first adoption signal) ---
  {
    auto in = proto::parse_inbound(R"({"type":"registered","adoption_state":"pending"})");
    assert(in.type == proto::InboundType::Registered);
    assert(in.adoption_state == "pending");
  }

  // --- Inbound: state_update carries device_id filter key ---
  {
    auto in = proto::parse_inbound(
        R"({"type":"state_update","device_id":"dev-1","adoption_state":"adopted"})");
    assert(in.type == proto::InboundType::StateUpdate);
    assert(in.device_id == "dev-1");
    assert(in.adoption_state == "adopted");
  }

  // --- Inbound: gateway "state" (may be "thinking" — no local FSM equivalent) ---
  {
    auto in = proto::parse_inbound(R"({"type":"state","session_id":"s1","state":"thinking"})");
    assert(in.type == proto::InboundType::GatewayState);
    assert(in.gateway_state == "thinking");
    assert(in.session_id == "s1");
  }

  // --- Inbound: command ---
  {
    auto in = proto::parse_inbound(
        R"({"type":"command","request_id":"r2","verb":"ping","args":{}})");
    assert(in.type == proto::InboundType::Command);
    assert(in.request_id == "r2");
    assert(in.verb == "ping");
  }

  // --- Forward-compat: unknown type + malformed JSON never throw ---
  {
    assert(proto::parse_inbound(R"({"type":"future_thing"})").type ==
           proto::InboundType::Unknown);
    assert(proto::parse_inbound("not json").type == proto::InboundType::ParseError);
    assert(proto::parse_inbound(R"({"no":"type"})").type == proto::InboundType::ParseError);
  }

  std::puts("test_proto OK");
  return 0;
}
