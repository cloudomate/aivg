import { describe, it, expect, vi } from "vitest";
import { ConfigClient, ConfigVersionConflict } from "../../src/config";
import type { SatelliteConfigWire } from "../../src/proto/ws-messages";

const wire: SatelliteConfigWire = {
  wake_word: "Hey Jarvis",
  routing_mode: "preferred",
  log_level: "INFO",
  heartbeat_interval: 30,
  extra: { mode: "test" },
  version: 7,
};

function jsonResp(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("ConfigClient — shape mapping", () => {
  it("wireToPublic snake_case → camelCase", () => {
    const p = ConfigClient.wireToPublic(wire);
    expect(p.wakeWord).toBe("Hey Jarvis");
    expect(p.routingMode).toBe("preferred");
    expect(p.logLevel).toBe("info");
    expect(p.heartbeatInterval).toBe(30);
    expect(p.version).toBe(7);
    expect(p.extra.mode).toBe("test");
  });

  it("publicPatchToWire camelCase → snake_case", () => {
    const w = ConfigClient.publicPatchToWire({
      wakeWord: "Compy",
      logLevel: "debug",
      heartbeatInterval: 60,
    });
    expect(w.wake_word).toBe("Compy");
    expect(w.log_level).toBe("DEBUG");
    expect(w.heartbeat_interval).toBe(60);
  });

  it("publicPatchToWire elides absent fields", () => {
    const w = ConfigClient.publicPatchToWire({});
    expect(Object.keys(w)).toHaveLength(0);
  });
});

describe("ConfigClient — GET /satellite/{id}/config", () => {
  it("happy path returns mapped config", async () => {
    const fetchFn = vi.fn(async () => jsonResp(200, wire)) as unknown as typeof fetch;
    const c = new ConfigClient({ gatewayUrl: "http://gw", deviceId: "d1", fetchFn });
    const out = await c.get();
    expect(out.wakeWord).toBe("Hey Jarvis");
    expect(fetchFn).toHaveBeenCalledTimes(1);
  });

  it("HTTP error → signaling_failed", async () => {
    const fetchFn = vi.fn(async () => new Response("nope", { status: 500 })) as unknown as typeof fetch;
    const c = new ConfigClient({ gatewayUrl: "http://gw", deviceId: "d1", fetchFn });
    await expect(c.get()).rejects.toMatchObject({ code: "signaling_failed" });
  });
});

describe("ConfigClient — POST /satellite/{id}/config", () => {
  it("requires a version — fetches first if cache is empty", async () => {
    const versions = [7, 8];
    const fetchFn = vi.fn(async (_url, _init?: RequestInit) => {
      const v = versions.shift()!;
      return jsonResp(200, { ...wire, version: v });
    }) as unknown as typeof fetch;
    const c = new ConfigClient({ gatewayUrl: "http://gw", deviceId: "d1", fetchFn });
    const out = await c.patch({ logLevel: "debug" });
    // First GET, then POST → 2 calls.
    expect((fetchFn as unknown as { mock: { calls: unknown[] } }).mock.calls.length).toBe(2);
    expect(out.version).toBe(8);
  });

  it("uses cached version when available", async () => {
    const fetchFn = vi.fn(async () => jsonResp(200, { ...wire, version: 9 })) as unknown as typeof fetch;
    const c = new ConfigClient({ gatewayUrl: "http://gw", deviceId: "d1", fetchFn });
    c.cacheChanged(ConfigClient.wireToPublic(wire));
    const out = await c.patch({ logLevel: "warn" });
    expect((fetchFn as unknown as { mock: { calls: unknown[] } }).mock.calls.length).toBe(1);
    expect(out.version).toBe(9);
  });

  it("409 → ConfigVersionConflict with current_version", async () => {
    const fetchFn = vi.fn(async () =>
      jsonResp(409, { error: { code: "version_conflict", current_version: 12 } }),
    ) as unknown as typeof fetch;
    const c = new ConfigClient({ gatewayUrl: "http://gw", deviceId: "d1", fetchFn });
    c.cacheChanged(ConfigClient.wireToPublic(wire));
    try {
      await c.patch({ logLevel: "error" });
      throw new Error("should have thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(ConfigVersionConflict);
      expect((err as ConfigVersionConflict).currentVersion).toBe(12);
    }
  });
});
