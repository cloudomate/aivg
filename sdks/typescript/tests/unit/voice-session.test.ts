import { describe, it, expect, vi } from "vitest";
import { InternalVoiceSession } from "../../src/voice-session";
import { Signaling } from "../../src/signaling";
import { FakePC, fakeAudioTrack, FakeMediaStream } from "../helpers/fake-webrtc";
import { EventBus, type SatelliteEvents } from "../../src/events";
import type { AudioSink } from "../../src/webrtc/injectable";

interface Captured {
  events: { name: string; payload: unknown }[];
  sink: AudioSink & { attached: MediaStream[]; detachCalls: number };
  pcRef: { current: FakePC | null };
  fsm: { connected: number; firstRemoteAudio: number; ended: number };
}

function buildSession(
  micStream: MediaStream,
  answerOk = true,
): { session: InternalVoiceSession; captured: Captured } {
  const bus = new EventBus<SatelliteEvents>();
  const captured: Captured = {
    events: [],
    sink: {
      attached: [],
      detachCalls: 0,
      attach(s: MediaStream) {
        this.attached.push(s);
      },
      detach() {
        this.detachCalls += 1;
      },
    },
    pcRef: { current: null },
    fsm: { connected: 0, firstRemoteAudio: 0, ended: 0 },
  };
  for (const k of [
    "session_started",
    "session_ended",
    "remote_stream",
    "error",
    "transient_error",
  ] as const) {
    bus.on(k, (p) => captured.events.push({ name: k, payload: p }));
  }

  const fakeFetch = vi.fn(async () =>
    answerOk
      ? new Response(
          JSON.stringify({
            device_id: "d1",
            session_id: "sess-1",
            sdp: "v=0\r\n",
            type: "answer",
          }),
          { status: 200 },
        )
      : new Response("nope", { status: 500 }),
  ) as unknown as typeof fetch;

  const signaling = new Signaling({ gatewayUrl: "http://gw", fetchFn: fakeFetch });

  const session = new InternalVoiceSession({
    gatewayUrl: "http://gw",
    deviceId: "d1",
    bus,
    webrtcFactory: () => {
      const pc = new FakePC();
      captured.pcRef.current = pc;
      // Auto-complete gathering immediately so the wait resolves fast.
      queueMicrotask(() => pc.completeGathering());
      return pc as unknown as RTCPeerConnection;
    },
    audioSinkFactory: () => captured.sink,
    micConstraints: { echoCancellation: true },
    getUserMediaFn: async () => micStream,
    signaling,
    iceGatherTimeoutMs: 1000,
    onSessionConnected: () => {
      captured.fsm.connected += 1;
    },
    onFirstRemoteAudio: () => {
      captured.fsm.firstRemoteAudio += 1;
    },
    onSessionEnded: () => {
      captured.fsm.ended += 1;
    },
  });
  return { session, captured };
}

describe("InternalVoiceSession", () => {
  it("happy path: mic + offer + answer → session_started + connected hook", async () => {
    const mic = new FakeMediaStream([fakeAudioTrack()]) as unknown as MediaStream;
    const { session, captured } = buildSession(mic);
    await session.start();
    captured.pcRef.current!.setConnectionState("connected");
    expect(captured.fsm.connected).toBe(1);
    const started = captured.events.find((e) => e.name === "session_started");
    expect(started).toBeDefined();
    expect((started?.payload as { sessionId: string }).sessionId).toBe("sess-1");
  });

  it("forwards first remote audio → onFirstRemoteAudio + remote_stream event", async () => {
    const mic = new FakeMediaStream([fakeAudioTrack()]) as unknown as MediaStream;
    const { session, captured } = buildSession(mic);
    await session.start();
    const remote = new FakeMediaStream([fakeAudioTrack()]) as unknown as MediaStream;
    captured.pcRef.current!.emitRemoteTrack(remote);
    expect(captured.fsm.firstRemoteAudio).toBe(1);
    expect(captured.sink.attached.length).toBe(1);
    expect(captured.events.find((e) => e.name === "remote_stream")).toBeDefined();
  });

  it("second remote-track event does NOT double-fire firstRemoteAudio", async () => {
    const mic = new FakeMediaStream([fakeAudioTrack()]) as unknown as MediaStream;
    const { session, captured } = buildSession(mic);
    await session.start();
    const r1 = new FakeMediaStream([fakeAudioTrack()]) as unknown as MediaStream;
    const r2 = new FakeMediaStream([fakeAudioTrack()]) as unknown as MediaStream;
    captured.pcRef.current!.emitRemoteTrack(r1);
    captured.pcRef.current!.emitRemoteTrack(r2);
    expect(captured.fsm.firstRemoteAudio).toBe(1);
  });

  it("close() stops mic tracks + detaches sink + closes PC", async () => {
    const audioTrack = fakeAudioTrack();
    const stopSpy = vi.spyOn(audioTrack, "stop");
    const mic = new FakeMediaStream([audioTrack]) as unknown as MediaStream;
    const { session, captured } = buildSession(mic);
    await session.start();
    session.close("operator_ended");
    expect(stopSpy).toHaveBeenCalled();
    expect(captured.sink.detachCalls).toBe(1);
    expect(captured.pcRef.current!.closeCalls).toBeGreaterThanOrEqual(1);
    expect(captured.fsm.ended).toBe(1);
  });

  it("signaling failure → emits error + ends the session", async () => {
    const mic = new FakeMediaStream([fakeAudioTrack()]) as unknown as MediaStream;
    const { session, captured } = buildSession(mic, /* answerOk */ false);
    await expect(session.start()).rejects.toMatchObject({ code: "signaling_failed" });
    expect(captured.events.find((e) => e.name === "error")).toBeDefined();
    expect(captured.fsm.ended).toBeGreaterThanOrEqual(1);
  });

  it("ICE connection failure → emits ice_failed", async () => {
    const mic = new FakeMediaStream([fakeAudioTrack()]) as unknown as MediaStream;
    const { session, captured } = buildSession(mic);
    await session.start();
    captured.pcRef.current!.setConnectionState("failed");
    const err = captured.events.find((e) => e.name === "error");
    expect(err).toBeDefined();
    expect((err?.payload as { code: string }).code).toBe("ice_failed");
  });

  it("getUserMedia permission denied → permission_denied", async () => {
    const bus = new EventBus<SatelliteEvents>();
    const errors: unknown[] = [];
    bus.on("error", (e) => errors.push(e));
    const denied = Object.assign(new Error("denied"), { name: "NotAllowedError" });
    const session = new InternalVoiceSession({
      gatewayUrl: "http://gw",
      deviceId: "d1",
      bus,
      webrtcFactory: () => new FakePC() as unknown as RTCPeerConnection,
      audioSinkFactory: () => ({ attach: () => {}, detach: () => {} }),
      micConstraints: {},
      getUserMediaFn: () => Promise.reject(denied),
      signaling: new Signaling({
        gatewayUrl: "http://gw",
        fetchFn: vi.fn() as unknown as typeof fetch,
      }),
      onSessionConnected: () => {},
      onFirstRemoteAudio: () => {},
      onSessionEnded: () => {},
    });
    await expect(session.start()).rejects.toMatchObject({ code: "permission_denied" });
    expect(errors.length).toBe(1);
  });
});
