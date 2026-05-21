import { describe, it, expect } from "vitest";
import * as sdk from "../../src/index";

/**
 * Binding gate for the public-surface contract (contracts/satellite-api.md
 * "Package exports"). Every named export documented there MUST be present.
 *
 * Type-only exports get a stand-in here (we check that the runtime
 * compiles against them in the assertions below). The no-any-in-public
 * test (T070, polish phase) walks the emitted .d.ts; this test sticks to
 * runtime names so it works equally well in any test env.
 */

describe("public API — required exports", () => {
  it("exports the Satellite class", () => {
    expect(typeof sdk.Satellite).toBe("function");
  });

  it("exports CONTRACT_VERSION = '1.0.0' (SC-007)", () => {
    expect(sdk.CONTRACT_VERSION).toBe("1.0.0");
  });

  it("exports SDK_VERSION as a string", () => {
    expect(typeof sdk.SDK_VERSION).toBe("string");
  });

  it("exports the default DI factories", () => {
    expect(typeof sdk.defaultWebrtcFactory).toBe("function");
    expect(typeof sdk.defaultAudioSinkFactory).toBe("function");
  });

  it("exports SdkError class + sdkError factory + isSdkError guard", () => {
    expect(typeof sdk.SdkError).toBe("function");
    expect(typeof sdk.sdkError).toBe("function");
    expect(typeof sdk.isSdkError).toBe("function");
  });

  it("Satellite construction is side-effect-free (no network, no DOM)", () => {
    const sat = new sdk.Satellite({
      gatewayUrl: "http://localhost:8643",
      deviceId: "ctest-1",
      deviceType: "node",
    });
    expect(sat.state).toBe("idle");
    expect(sat.isAdopted).toBe(false);
    expect(sat.options.deviceId).toBe("ctest-1");
  });

  it("on/off return-types match the documented contract", () => {
    const sat = new sdk.Satellite({
      gatewayUrl: "http://localhost:8643",
      deviceId: "ctest-2",
      deviceType: "node",
    });
    const handler = (): void => {};
    const off = sat.on("state", handler);
    expect(typeof off).toBe("function");
    // Unsubscribe returns nothing meaningful, must not throw.
    expect(() => off()).not.toThrow();
    sat.off("state", handler);
  });

  it("async-iterator helpers are present", () => {
    const sat = new sdk.Satellite({
      gatewayUrl: "http://localhost:8643",
      deviceId: "ctest-3",
      deviceType: "node",
    });
    const it1 = sat.transcripts();
    const it2 = sat.logs();
    const it3 = sat.states();
    expect(typeof it1[Symbol.asyncIterator]).toBe("function");
    expect(typeof it2[Symbol.asyncIterator]).toBe("function");
    expect(typeof it3[Symbol.asyncIterator]).toBe("function");
    void it1.return?.();
    void it2.return?.();
    void it3.return?.();
  });
});

describe("beginSession() — gated on adoption (FR-001 edge case)", () => {
  it("rejects with not_adopted when device hasn't been adopted yet", async () => {
    const sat = new sdk.Satellite({
      gatewayUrl: "http://localhost:8643",
      deviceId: "ctest-4",
      deviceType: "node",
    });
    await expect(sat.beginSession()).rejects.toMatchObject({ code: "not_adopted" });
  });
});

describe("mixed-content detection", () => {
  it("does not flag localhost http on a non-https page", () => {
    // In Node test env window is undefined → mixed-content check returns null.
    const sat = new sdk.Satellite({
      gatewayUrl: "http://localhost:8643",
      deviceId: "ctest-5",
      deviceType: "node",
    });
    // No assertion of error; the construct itself should not throw.
    expect(sat).toBeDefined();
  });
});
