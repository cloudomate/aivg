// libaivg-sat — WebRTC signaling client (feature 020, T016, internal).
//
// Posts the libpeer-generated offer to the gateway's voice-plane endpoint
// and returns the answer. Mirrors sdks/typescript/src/proto/rest-shapes.ts
// (OfferRequest / OfferResponse). No new wire surface (FR-009/011).
#ifndef AIVG_SAT_SIGNALING_HPP
#define AIVG_SAT_SIGNALING_HPP

#include <string>

namespace aivg::sat::detail {

struct OfferResult {
  bool ok = false;
  std::string session_id;  // fabricated locally if the gateway omits it (FR-011)
  std::string sdp;         // answer SDP
  std::string error;
};

// POST {device_id, sdp, type:"offer"} to <signaling_base>/webrtc/offer
// (http:// only for now; matches the gateway's plaintext voice-plane port).
// Parses {device_id, session_id, sdp, type:"answer"}.
OfferResult post_offer(const std::string& signaling_base, const std::string& device_id,
                       const std::string& offer_sdp);

}  // namespace aivg::sat::detail

#endif  // AIVG_SAT_SIGNALING_HPP
