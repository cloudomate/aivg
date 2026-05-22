// libaivg-sat — gateway-pushed wire shapes (feature 020).
//
// These mirror the contract-`0.2.0` structures the gateway sends over
// the control plane, byte-shape-equal to @aivg/sat-sdk
// (`sdks/typescript/src/proto/` + `events.ts`) and the constitution's
// Appendix-B models (Principle II). Field-level parity is asserted in
// task T032. (De)serialization glue lives in src/proto/ (later tasks).
#ifndef AIVG_SAT_WIRE_HPP
#define AIVG_SAT_WIRE_HPP

#include <cstdint>
#include <map>
#include <string>

namespace aivg::sat {

// Gateway-pushed device config (delivered via the `config_changed` event).
struct SatelliteConfig {
  std::string wake_word;
  std::string routing_mode;
  std::string log_level;
  std::map<std::string, std::string> extra;  // forward-compatible passthrough
};

// A forwarded gateway log line (Principle II — identical across satellites).
struct LogEntry {
  double ts = 0.0;
  std::string level;
  std::string source;
  std::string msg;
  std::map<std::string, std::string> meta;
};

// OTA descriptors — forwarded to the consumer; the SDK implements no OTA
// flow (spec OOS-005).
struct OtaManifest {
  std::string version;
  std::string url;
  std::string sha256;
};

struct OtaProgress {
  std::string phase;
  std::uint8_t percent = 0;
};

}  // namespace aivg::sat

#endif  // AIVG_SAT_WIRE_HPP
