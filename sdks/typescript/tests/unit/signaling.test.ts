import { describe, it, expect, vi } from "vitest";
import { Signaling, waitForIceGatheringComplete } from "../../src/signaling";
import { FakePC } from "../helpers/fake-webrtc";
import { SdkError } from "../../src/errors";

describe("Signaling.postOffer", () => {
  it("happy path: posts JSON and returns the answer", async () => {
    const fakeAnswer = { device_id: "d1", session_id: "s1", sdp: "v=0…", type: "answer" };
    const fetchFn = vi.fn(
      async (_url: string, _init?: RequestInit): Promise<Response> => {
        return new Response(JSON.stringify(fakeAnswer), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      },
    ) as unknown as typeof fetch;
    const s = new Signaling({ gatewayUrl: "http://gw", fetchFn });
    const out = await s.postOffer({ deviceId: "d1", sdp: "v=0…" });
    expect(out.session_id).toBe("s1");
    expect(out.sdp).toBe("v=0…");
  });

  it("HTTP non-2xx → signaling_failed", async () => {
    const fetchFn = vi.fn(async () => new Response("nope", { status: 500 })) as unknown as typeof fetch;
    const s = new Signaling({ gatewayUrl: "http://gw", fetchFn });
    await expect(s.postOffer({ deviceId: "d1", sdp: "v=0" })).rejects.toMatchObject({
      code: "signaling_failed",
    });
  });

  it("non-JSON body → signaling_failed", async () => {
    const fetchFn = vi.fn(
      async () => new Response("not json", { status: 200 }),
    ) as unknown as typeof fetch;
    const s = new Signaling({ gatewayUrl: "http://gw", fetchFn });
    await expect(s.postOffer({ deviceId: "d1", sdp: "v=0" })).rejects.toMatchObject({
      code: "signaling_failed",
    });
  });

  it("response missing required fields → signaling_failed", async () => {
    const fetchFn = vi.fn(
      async () =>
        new Response(JSON.stringify({ sdp: "v=0", type: "answer" }), { status: 200 }),
    ) as unknown as typeof fetch;
    const s = new Signaling({ gatewayUrl: "http://gw", fetchFn });
    await expect(s.postOffer({ deviceId: "d1", sdp: "v=0" })).rejects.toMatchObject({
      code: "signaling_failed",
    });
  });

  it("network error → signaling_failed (not timeout)", async () => {
    const fetchFn = vi.fn(async () => {
      throw new Error("ECONNREFUSED");
    }) as unknown as typeof fetch;
    const s = new Signaling({ gatewayUrl: "http://gw", fetchFn });
    await expect(s.postOffer({ deviceId: "d1", sdp: "v=0" })).rejects.toMatchObject({
      code: "signaling_failed",
    });
  });

  it("AbortError → ice_gathering_timeout", async () => {
    const fetchFn = vi.fn(async () => {
      const err = new Error("aborted");
      err.name = "AbortError";
      throw err;
    }) as unknown as typeof fetch;
    const s = new Signaling({ gatewayUrl: "http://gw", fetchFn });
    await expect(
      s.postOffer({ deviceId: "d1", sdp: "v=0", timeoutMs: 10 }),
    ).rejects.toMatchObject({ code: "ice_gathering_timeout" });
  });
});

describe("waitForIceGatheringComplete", () => {
  it("resolves immediately if already complete", async () => {
    const pc = new FakePC();
    pc.iceGatheringState = "complete";
    await expect(
      waitForIceGatheringComplete(pc as unknown as RTCPeerConnection, 1000),
    ).resolves.toBeUndefined();
  });

  it("resolves when state transitions to complete", async () => {
    const pc = new FakePC();
    const p = waitForIceGatheringComplete(pc as unknown as RTCPeerConnection, 1000);
    // Fire the listener via the FakePC's helper.
    pc.completeGathering();
    await expect(p).resolves.toBeUndefined();
  });

  it("rejects with ice_gathering_timeout after timeout", async () => {
    const pc = new FakePC();
    // pc stays in "new" forever.
    await expect(
      waitForIceGatheringComplete(pc as unknown as RTCPeerConnection, 5),
    ).rejects.toMatchObject({ code: "ice_gathering_timeout" });
  });

  it("the rejected error is an SdkError instance", async () => {
    const pc = new FakePC();
    let caught: unknown = null;
    try {
      await waitForIceGatheringComplete(pc as unknown as RTCPeerConnection, 5);
    } catch (err) {
      caught = err;
    }
    expect(caught).toBeInstanceOf(SdkError);
  });
});
