/**
 * REST request/response shapes per
 * `specs/014-aivg-sat-sdk-ts/contracts/wire-protocol.md` "HTTP shapes".
 *
 * Endpoints the SDK CALLS:
 *  - POST /satellite/register
 *  - GET  /satellite/{id}/config
 *  - POST /satellite/{id}/config
 *  - POST /webrtc/offer
 *  - POST /webrtc/candidate   (fallback only; R-7)
 *
 * The SDK does NOT call /satellite/list, /satellite/{id}/adopt,
 * /satellite/{id}/command, /satellite/{id}/ota/*, /satellite/logs —
 * those are operator-side surfaces.
 */

import type { SatelliteConfigWire } from "./ws-messages";

// ---------- POST /satellite/register --------------------------------

export interface RegisterRequest {
  device_id: string;
  name: string;
  device_type: string;
  firmware_version: string;
  contract_version: string;
  capabilities: {
    aec?: "browser_aec3" | "hardware_xmos" | "software_speex" | "half_duplex";
    wake_word?: string;
    [k: string]: unknown;
  };
}

export interface RegisterResponse {
  device_id: string;
  adoption_state: "pending" | "adopted";
}

// ---------- GET/POST /satellite/{id}/config -------------------------

export type ConfigGetResponse = SatelliteConfigWire;

export interface ConfigPostRequest {
  patch: Partial<Omit<SatelliteConfigWire, "version">>;
  if_match_version: number;
}

export type ConfigPostResponse = SatelliteConfigWire;

export interface ConfigConflictResponse {
  error: {
    code: "version_conflict";
    current_version: number;
  };
}

// ---------- POST /webrtc/offer --------------------------------------

export interface OfferRequest {
  device_id: string;
  sdp: string;
  type: "offer";
}

export interface OfferResponse {
  device_id: string;
  session_id: string;
  sdp: string;
  type: "answer";
}

// ---------- POST /webrtc/candidate (fallback) -----------------------

export interface CandidateRequest {
  device_id: string;
  candidate: string;
  sdp_mid: string;
  sdp_m_line_index: number;
}
