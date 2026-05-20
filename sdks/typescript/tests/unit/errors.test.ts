import { describe, it, expect } from "vitest";
import { SdkError, sdkError, isSdkError, type SdkErrorCode } from "../../src/errors";

describe("SdkError", () => {
  it("is an Error and an SdkError", () => {
    const err = sdkError("ice_failed", "no candidates");
    expect(err).toBeInstanceOf(Error);
    expect(err).toBeInstanceOf(SdkError);
    expect(isSdkError(err)).toBe(true);
  });

  it("non-SdkError is not detected as SdkError", () => {
    expect(isSdkError(new Error("hi"))).toBe(false);
    expect(isSdkError("string")).toBe(false);
    expect(isSdkError(null)).toBe(false);
    expect(isSdkError(undefined)).toBe(false);
  });

  it("preserves code + message + ts + cause", () => {
    const cause = new Error("underlying");
    const err = sdkError("permission_denied", "user denied mic", cause);
    expect(err.code).toBe("permission_denied");
    expect(err.message).toBe("user denied mic");
    expect(err.cause).toBe(cause);
    expect(typeof err.ts).toBe("number");
    expect(err.ts).toBeGreaterThan(0);
  });

  it("omits cause when not provided", () => {
    const err = sdkError("ice_failed", "no candidates");
    expect(err.cause).toBeUndefined();
  });

  // Closed-set discriminant — adding/removing a code is a SemVer event.
  it("exposes the closed SdkErrorCode set", () => {
    const codes: SdkErrorCode[] = [
      "no_webrtc_impl",
      "no_microphone_api",
      "permission_denied",
      "ice_failed",
      "ice_gathering_timeout",
      "ws_disconnected",
      "ws_max_retries_exceeded",
      "signaling_failed",
      "mixed_content",
      "not_adopted",
      "protocol_mismatch",
      "duplicate_device",
    ];
    // Round-trip every code — TS catches typos at compile time; this
    // also serves as a checksum for the closed-set contract test.
    for (const c of codes) {
      const e = sdkError(c, `test ${c}`);
      expect(e.code).toBe(c);
    }
    expect(codes).toHaveLength(12);
  });
});
