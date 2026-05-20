import { describe, it, expect } from "vitest";
import {
  KNOWN_COMMAND_VERBS,
  isKnownVerb,
  commandResult,
  type CommandVerb,
} from "../../src/commands";
import {
  ControlPlane,
  type WebSocketLike,
  type ControlPlaneOptions,
} from "../../src/control-plane";
import { EventBus, type SatelliteEvents, type CommandEvent } from "../../src/events";

describe("commands — closed-set verb validator", () => {
  it("includes the 5 documented verbs", () => {
    expect(KNOWN_COMMAND_VERBS).toEqual([
      "reboot",
      "restart",
      "refresh_config",
      "tail_logs",
      "ping",
    ]);
  });

  it.each(KNOWN_COMMAND_VERBS)("isKnownVerb('%s') === true", (verb: CommandVerb) => {
    expect(isKnownVerb(verb)).toBe(true);
  });

  it("isKnownVerb('shutdown') === false", () => {
    expect(isKnownVerb("shutdown")).toBe(false);
  });
});

describe("commands — commandResult helpers", () => {
  it("ok() with no args yields a minimal success payload", () => {
    expect(commandResult.ok()).toEqual({ ok: true });
  });

  it("ok(message, data) carries both", () => {
    const r = commandResult.ok("done", { foo: 1 });
    expect(r).toEqual({ ok: true, message: "done", data: { foo: 1 } });
  });

  it("fail(message) yields ok=false + message", () => {
    expect(commandResult.fail("nope")).toEqual({ ok: false, message: "nope" });
  });
});

// ----------- end-to-end via control-plane -------------------------------

class FakeWS implements WebSocketLike {
  static instances: FakeWS[] = [];
  public readonly url: string;
  public readyState = 0;
  public onopen: WebSocketLike["onopen"] = null;
  public onclose: WebSocketLike["onclose"] = null;
  public onerror: WebSocketLike["onerror"] = null;
  public onmessage: WebSocketLike["onmessage"] = null;
  public readonly sent: string[] = [];
  constructor(url: string) {
    this.url = url;
    FakeWS.instances.push(this);
  }
  send(data: string): void {
    this.sent.push(data);
  }
  close(): void {
    this.readyState = 3;
    this.onclose?.call(this, { code: 1000 } as CloseEvent);
  }
  triggerOpen(): void {
    this.readyState = 1;
    this.onopen?.call(this, new Event("open"));
  }
  triggerMessage(raw: string): void {
    this.onmessage?.call(this, { data: raw } as MessageEvent<string>);
  }
}

describe("control-plane → command dispatch + reply", () => {
  it("dispatches an inbound `command` and round-trips the reply", () => {
    FakeWS.instances = [];
    const bus = new EventBus<SatelliteEvents>();
    const captured: CommandEvent[] = [];
    bus.on("command", (e) => captured.push(e));
    const cp = new ControlPlane({
      gatewayUrl: "http://localhost:8643",
      deviceId: "dev-cmd",
      bus,
      getState: () => "idle",
      firmwareVersion: "0.0.1",
      wsFactory: ((url: string) => new FakeWS(url)) as unknown as ControlPlaneOptions["wsFactory"],
    });
    void cp.start();
    const ws = FakeWS.instances[0]!;
    ws.triggerOpen();
    ws.triggerMessage(
      JSON.stringify({
        type: "command",
        request_id: "req-7",
        verb: "ping",
        args: { from: "operator" },
      }),
    );
    expect(captured).toHaveLength(1);
    expect(captured[0]!.verb).toBe("ping");
    expect(captured[0]!.args).toEqual({ from: "operator" });

    // Reply, then verify command_result was sent back over WS.
    captured[0]!.reply(commandResult.ok("pong", { latency_ms: 5 }));
    const replyMsg = ws.sent.find((s) => s.includes('"command_result"'));
    expect(replyMsg).toBeDefined();
    const parsed = JSON.parse(replyMsg!) as {
      type: string;
      request_id: string;
      ok: boolean;
      message?: string;
      data?: Record<string, unknown>;
    };
    expect(parsed.type).toBe("command_result");
    expect(parsed.request_id).toBe("req-7");
    expect(parsed.ok).toBe(true);
    expect(parsed.message).toBe("pong");
    expect(parsed.data).toEqual({ latency_ms: 5 });
    cp.stop();
  });
});
