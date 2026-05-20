/**
 * WebRTC signaling — POST /webrtc/offer (R-7: full-gather then offer).
 *
 * Per spec FR-008 / contracts/wire-protocol.md:
 *   request:  { device_id, sdp, type: "offer" }
 *   response: { device_id, session_id, sdp, type: "answer" }
 */

import { sdkError } from "./errors";
import type { OfferRequest, OfferResponse } from "./proto/rest-shapes";

export interface SignalingOptions {
  gatewayUrl: string;
  /** Inject for tests; defaults to globalThis.fetch. */
  fetchFn?: typeof fetch;
  /** Inject for tests; defaults to AbortController. */
  AbortControllerCtor?: typeof AbortController;
}

export interface PostOfferArgs {
  deviceId: string;
  sdp: string;
  /** Hard timeout for the HTTP exchange. Default 10 000 ms. */
  timeoutMs?: number;
}

export class Signaling {
  private readonly gatewayUrl: string;
  private readonly fetchFn: typeof fetch;
  private readonly AbortControllerCtor: typeof AbortController;

  constructor(opts: SignalingOptions) {
    this.gatewayUrl = opts.gatewayUrl.replace(/\/+$/, "");
    this.fetchFn = opts.fetchFn ?? globalThis.fetch.bind(globalThis);
    this.AbortControllerCtor = opts.AbortControllerCtor ?? AbortController;
  }

  async postOffer(args: PostOfferArgs): Promise<OfferResponse> {
    const url = `${this.gatewayUrl}/webrtc/offer`;
    const body: OfferRequest = {
      device_id: args.deviceId,
      sdp: args.sdp,
      type: "offer",
    };
    const timeoutMs = args.timeoutMs ?? 10_000;
    const ctrl = new this.AbortControllerCtor();
    const handle = setTimeout(() => ctrl.abort(), timeoutMs);
    let resp: Response;
    try {
      resp = await this.fetchFn(url, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });
    } catch (err) {
      const isAbort =
        err instanceof Error && (err.name === "AbortError" || err.name === "TimeoutError");
      if (isAbort) {
        throw sdkError("ice_gathering_timeout", `POST ${url} timed out after ${timeoutMs}ms`);
      }
      throw sdkError("signaling_failed", `POST ${url} failed: ${String(err)}`, err);
    } finally {
      clearTimeout(handle);
    }
    if (!resp.ok) {
      throw sdkError(
        "signaling_failed",
        `POST ${url} → HTTP ${resp.status} ${resp.statusText}`,
      );
    }
    let payload: unknown;
    try {
      payload = (await resp.json()) as unknown;
    } catch (err) {
      throw sdkError("signaling_failed", `POST ${url} non-JSON response`, err);
    }
    // Light shape check — full validation is the gateway's job (R-8).
    const obj = payload as Partial<OfferResponse>;
    if (
      typeof obj.sdp !== "string" ||
      obj.type !== "answer" ||
      typeof obj.session_id !== "string"
    ) {
      throw sdkError("signaling_failed", `POST ${url} bad response shape`, payload);
    }
    return obj as OfferResponse;
  }
}

/**
 * Wait until the peer connection's iceGatheringState reaches "complete",
 * or reject with `ice_gathering_timeout` if it doesn't within timeoutMs.
 *
 * Exported so unit tests can drive a FakePC through the same wait path.
 */
export function waitForIceGatheringComplete(
  pc: RTCPeerConnection,
  timeoutMs: number,
): Promise<void> {
  if (pc.iceGatheringState === "complete") return Promise.resolve();
  return new Promise<void>((resolve, reject) => {
    const handle = setTimeout(() => {
      pc.removeEventListener("icegatheringstatechange", check);
      reject(sdkError("ice_gathering_timeout", `ICE gathering timeout after ${timeoutMs}ms`));
    }, timeoutMs);
    const check = (): void => {
      if (pc.iceGatheringState === "complete") {
        clearTimeout(handle);
        pc.removeEventListener("icegatheringstatechange", check);
        resolve();
      }
    };
    pc.addEventListener("icegatheringstatechange", check);
  });
}
