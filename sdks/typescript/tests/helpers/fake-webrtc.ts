/**
 * In-process fake of the W3C `RTCPeerConnection` subset the SDK uses.
 *
 * Documented contract: `specs/014-aivg-sat-sdk-ts/contracts/webrtc-injection.md`.
 *
 * This fake is NOT exported by the published package. Third-party tests
 * implementing the same subset against `RTCPeerConnection` is the
 * contract — we don't promise this exact class.
 *
 * Capabilities:
 *  - addTrack / addTransceiver (records, no real media flows)
 *  - createOffer / setLocalDescription / setRemoteDescription
 *  - iceGatheringState: starts "new"; tests drive transitions via
 *    `completeGathering()` to mimic the browser's async candidate flow
 *  - connectionState: starts "new"; tests drive via `setConnectionState()`
 *  - ontrack: tests can fire a synthetic remote track via `emitRemoteTrack()`
 *  - close(): records, idempotent
 */
import { EventEmitter } from "node:events";

type SDPInit = { type: "offer" | "answer" | "pranswer" | "rollback"; sdp: string };

export class FakePC extends EventEmitter {
  public iceGatheringState: RTCIceGatheringState = "new";
  public iceConnectionState: RTCIceConnectionState = "new";
  public connectionState: RTCPeerConnectionState = "new";
  public signalingState: RTCSignalingState = "stable";

  public localDescription: SDPInit | null = null;
  public remoteDescription: SDPInit | null = null;

  // Recordings for assertions.
  public readonly addedTracks: MediaStreamTrack[] = [];
  public readonly addedTransceivers: { kind: string; init?: RTCRtpTransceiverInit }[] = [];
  public closeCalls = 0;

  // Event handlers (test code may assign these directly, mirroring the
  // browser API).
  public ontrack: ((ev: RTCTrackEvent) => void) | null = null;
  public onicegatheringstatechange: ((this: RTCPeerConnection, ev: Event) => void) | null = null;
  public oniceconnectionstatechange: ((this: RTCPeerConnection, ev: Event) => void) | null = null;
  public onconnectionstatechange: ((this: RTCPeerConnection, ev: Event) => void) | null = null;
  public onsignalingstatechange: ((this: RTCPeerConnection, ev: Event) => void) | null = null;
  public onicecandidate: ((ev: RTCPeerConnectionIceEvent) => void) | null = null;

  addTrack(track: MediaStreamTrack, ..._streams: MediaStream[]): RTCRtpSender {
    this.addedTracks.push(track);
    return {} as RTCRtpSender;
  }

  addTransceiver(kind: string, init?: RTCRtpTransceiverInit): RTCRtpTransceiver {
    this.addedTransceivers.push({ kind, init });
    return {} as RTCRtpTransceiver;
  }

  async createOffer(_opts?: RTCOfferOptions): Promise<SDPInit> {
    return { type: "offer", sdp: this.buildFakeSdp("offer") };
  }

  async setLocalDescription(desc: SDPInit): Promise<void> {
    this.localDescription = desc;
    this.signalingState = desc.type === "offer" ? "have-local-offer" : "stable";
    this.onsignalingstatechange?.call(
      this as unknown as RTCPeerConnection,
      new Event("signalingstatechange"),
    );
  }

  async setRemoteDescription(desc: SDPInit): Promise<void> {
    this.remoteDescription = desc;
    this.signalingState = desc.type === "answer" ? "stable" : "have-remote-offer";
    this.onsignalingstatechange?.call(
      this as unknown as RTCPeerConnection,
      new Event("signalingstatechange"),
    );
  }

  addEventListener(eventName: string, listener: (...args: unknown[]) => void): void {
    super.on(eventName, listener);
  }

  removeEventListener(eventName: string, listener: (...args: unknown[]) => void): void {
    super.off(eventName, listener);
  }

  close(): void {
    this.closeCalls++;
    this.connectionState = "closed";
    this.signalingState = "closed";
    this.onconnectionstatechange?.call(
      this as unknown as RTCPeerConnection,
      new Event("connectionstatechange"),
    );
  }

  // -------- test driver hooks ---------------------------------------

  completeGathering(): void {
    this.iceGatheringState = "complete";
    const ev = new Event("icegatheringstatechange");
    this.onicegatheringstatechange?.call(this as unknown as RTCPeerConnection, ev);
    // Also fire registered addEventListener-style listeners (the SDK
    // uses this style in src/signaling.ts).
    super.emit("icegatheringstatechange", ev);
  }

  setConnectionState(state: RTCPeerConnectionState): void {
    this.connectionState = state;
    const ev = new Event("connectionstatechange");
    this.onconnectionstatechange?.call(this as unknown as RTCPeerConnection, ev);
    super.emit("connectionstatechange", ev);
  }

  setIceConnectionState(state: RTCIceConnectionState): void {
    this.iceConnectionState = state;
    const ev = new Event("iceconnectionstatechange");
    this.oniceconnectionstatechange?.call(this as unknown as RTCPeerConnection, ev);
    super.emit("iceconnectionstatechange", ev);
  }

  emitRemoteTrack(stream: MediaStream): void {
    const fakeTrack = stream.getAudioTracks()[0] ?? ({ kind: "audio" } as MediaStreamTrack);
    const ev = { track: fakeTrack, streams: [stream] } as unknown as RTCTrackEvent;
    this.ontrack?.(ev);
  }

  private buildFakeSdp(kind: "offer" | "answer"): string {
    return [
      "v=0",
      `o=- 0 0 IN IP4 127.0.0.1`,
      `s=fake-${kind}`,
      "t=0 0",
      "m=audio 9 UDP/TLS/RTP/SAVPF 111",
      "a=rtpmap:111 opus/48000/2",
      "",
    ].join("\r\n");
  }
}

/** Factory matching `WebrtcFactory` so tests can pass it to `Satellite`. */
export const fakeWebrtcFactory = (): RTCPeerConnection =>
  new FakePC() as unknown as RTCPeerConnection;

/** Minimal MediaStream stub for environments without DOM (vitest unit env). */
export class FakeMediaStream {
  private readonly tracks: MediaStreamTrack[];
  constructor(tracks: MediaStreamTrack[] = []) {
    this.tracks = tracks;
  }
  getTracks(): MediaStreamTrack[] {
    return this.tracks.slice();
  }
  getAudioTracks(): MediaStreamTrack[] {
    return this.tracks.filter((t) => t.kind === "audio");
  }
}

export const fakeAudioTrack = (): MediaStreamTrack =>
  ({
    kind: "audio",
    enabled: true,
    id: `fake-track-${Math.random().toString(36).slice(2, 8)}`,
    stop: () => {},
  }) as unknown as MediaStreamTrack;
