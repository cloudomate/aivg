import { describe, it, expect, vi } from "vitest";
import { EventBus, iterate } from "../../src/events";

interface TestMap {
  greet: { name: string };
  shout: string;
  noop: undefined;
}

describe("EventBus", () => {
  it("dispatches to subscribed handler", () => {
    const bus = new EventBus<TestMap>();
    const seen: { name: string }[] = [];
    bus.on("greet", (p) => seen.push(p));
    bus.emit("greet", { name: "world" });
    expect(seen).toEqual([{ name: "world" }]);
  });

  it("ignores events with no listeners", () => {
    const bus = new EventBus<TestMap>();
    expect(() => bus.emit("greet", { name: "void" })).not.toThrow();
  });

  it("supports multiple handlers per event", () => {
    const bus = new EventBus<TestMap>();
    const a = vi.fn();
    const b = vi.fn();
    bus.on("shout", a);
    bus.on("shout", b);
    bus.emit("shout", "hi");
    expect(a).toHaveBeenCalledWith("hi");
    expect(b).toHaveBeenCalledWith("hi");
  });

  it("returns an unsubscribe fn from on()", () => {
    const bus = new EventBus<TestMap>();
    const fn = vi.fn();
    const off = bus.on("shout", fn);
    bus.emit("shout", "x");
    off();
    bus.emit("shout", "y");
    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenCalledWith("x");
  });

  it("off() removes a registered handler", () => {
    const bus = new EventBus<TestMap>();
    const fn = vi.fn();
    bus.on("shout", fn);
    bus.off("shout", fn);
    bus.emit("shout", "x");
    expect(fn).not.toHaveBeenCalled();
  });

  it("one bad handler does not break other handlers (EventTarget parity)", () => {
    const bus = new EventBus<TestMap>();
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const bad = vi.fn(() => {
      throw new Error("boom");
    });
    const good = vi.fn();
    bus.on("shout", bad);
    bus.on("shout", good);
    bus.emit("shout", "x");
    expect(bad).toHaveBeenCalled();
    expect(good).toHaveBeenCalled();
    expect(errSpy).toHaveBeenCalled();
    errSpy.mockRestore();
  });

  it("handler that unsubscribes mid-dispatch does not corrupt iteration", () => {
    const bus = new EventBus<TestMap>();
    const trail: string[] = [];
    let off1: (() => void) | null = null;
    off1 = bus.on("shout", (p) => {
      trail.push(`a:${p}`);
      off1?.();
    });
    bus.on("shout", (p) => trail.push(`b:${p}`));
    bus.emit("shout", "first");
    bus.emit("shout", "second");
    expect(trail).toEqual(["a:first", "b:first", "b:second"]);
  });
});

describe("iterate()", () => {
  it("yields events in order", async () => {
    const bus = new EventBus<TestMap>();
    const iter = iterate(bus, "shout");
    bus.emit("shout", "a");
    bus.emit("shout", "b");
    expect((await iter.next()).value).toBe("a");
    expect((await iter.next()).value).toBe("b");
    await iter.return!();
  });

  it("resolves a pending next() when an event arrives", async () => {
    const bus = new EventBus<TestMap>();
    const iter = iterate(bus, "shout");
    const p = iter.next();
    bus.emit("shout", "delayed");
    expect((await p).value).toBe("delayed");
    await iter.return!();
  });

  it("return() unsubscribes and ends the iterator", async () => {
    const bus = new EventBus<TestMap>();
    const iter = iterate(bus, "shout");
    await iter.return!();
    bus.emit("shout", "after-close");
    const r = await iter.next();
    expect(r.done).toBe(true);
  });
});
