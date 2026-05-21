// Stub — real defaultWebrtcFactory lands in T025 (Phase 3 / US1).
import { sdkError } from "../errors";
import type { WebrtcFactory } from "./injectable";

export const defaultWebrtcFactory: WebrtcFactory = () => {
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
  if (typeof globalThis.RTCPeerConnection !== "function") {
    throw sdkError(
      "no_webrtc_impl",
      "No RTCPeerConnection in this runtime — pass webrtcFactory to Satellite constructor",
    );
  }
  return new globalThis.RTCPeerConnection({ iceServers: [] });
};
