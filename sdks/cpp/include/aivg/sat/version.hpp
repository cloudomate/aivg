// libaivg-sat — version constants (feature 020).
//
// CONTRACT_VERSION mirrors `aivg --contract-version` and
// `sdks/typescript/src/proto/version.ts` EXACTLY. Shipping this SDK MUST
// NOT bump it (spec SC-006). Compatibility is keyed off the MAJOR
// component (FR-014).
#ifndef AIVG_SAT_VERSION_HPP
#define AIVG_SAT_VERSION_HPP

namespace aivg::sat {

inline constexpr const char* kContractVersion = "0.2.0";
inline constexpr const char* kSdkVersion = "0.1.0";

}  // namespace aivg::sat

#endif  // AIVG_SAT_VERSION_HPP
