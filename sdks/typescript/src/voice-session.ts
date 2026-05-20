/**
 * Per-call voice session lifecycle.
 *
 * Builds the WebRTC PeerConnection via the injected factory, attaches the
 * mic, runs full-gather ICE (R-7), posts the offer, applies the answer,
 * forwards the remote track to the audio sink, and watches the PC's
 * connectionState for `connected` → drives FSM `idle → listening`, and
 * for first inbound audio frame → drives FSM `listening → speaking`.
 *
 * Each session is exactly ONE PeerConnection (constitution III). Multiple
 * "turns" (user spoke → agent replied) can happen within one session.
 */

import { sdkError, type SdkError } from "./errors";
import { Signaling, waitForIceGatheringComplete } from "./signaling";
import type {
  WebrtcFactory,
  AudioSink,
  AudioSinkFactory,
} from "./webrtc/injectable";
import type {
  EventBus,
  SatelliteEvents,
  VoiceSession as VoiceSessionPublic,
  VoiceSessionResult,
} from "./events";

export interface VoiceSessionOptions {
  gatewayUrl: string;
  deviceId: string;
  bus: EventBus<SatelliteEvents>;
  webrtcFactory: WebrtcFactory;
  audioSinkFactory: AudioSinkFactory;
  micConstraints: MediaTrackConstraints;
  /** Inject for tests. Defaults to navigator.mediaDevices.getUserMedia. */
  getUserMediaFn?: (constraints: MediaStreamConstraints) => Promise<MediaStream>;
  /** Inject the Signaling driver for tests; defaults to a fresh one. */
  signaling?: Signaling;
  /** Hard cap on ICE gather wait. Default 5 000 ms (R-7). */
  iceGatherTimeoutMs?: number;
  /**
   * Hooks the owning Satellite uses to drive its FSM. We don't import the
   * FSM directly so the session module stays single-purpose.
   */
  onSessionConnected: () => void; // → "listening"
  onFirstRemoteAudio: () => void; // → "speaking"
  onSessionEnded: (reason: VoiceSessionResult["reason"], error?: SdkError) => void;
}

function defaultGetUserMedia(constraints: MediaStreamConstraints): Promise<MediaStream> {
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
  if (typeof navigator === "undefined" || !navigator.mediaDevices) {
    throw sdkError(
      "no_microphone_api",
      "No navigator.mediaDevices in this runtime — pass getUserMediaFn for Node/tests",
    );
  }
  return navigator.mediaDevices.getUserMedia(constraints);
}

export class InternalVoiceSession {
  public readonly sessionId: string = "";
  public readonly startedAt: number = Date.now();
  public readonly ended: Promise<VoiceSessionResult>;

  private readonly opts: VoiceSessionOptions;
  private readonly signaling: Signaling;
  private readonly endedResolve: (r: VoiceSessionResult) => void;
  private pc: RTCPeerConnection | null = null;
  private sink: AudioSink | null = null;
  private localStream: MediaStream | null = null;
  private gotFirstRemoteAudio = false;
  private active = true;
  private turnCount = 0;
  // Mutable session_id assigned by the gateway in the offer response.
  private resolvedSessionId = "";

  constructor(opts: VoiceSessionOptions) {
    this.opts = opts;
    this.signaling =
      opts.signaling ?? new Signaling({ gatewayUrl: opts.gatewayUrl });

    let resolve!: (r: VoiceSessionResult) => void;
    this.ended = new Promise<VoiceSessionResult>((r) => {
      resolve = r;
    });
    this.endedResolve = resolve;
  }

  /**
   * Drive the offer/answer + ICE flow to completion. On success the FSM
   * sits in `listening` and we're waiting for the first inbound audio.
   */
  async start(): Promise<void> {
    let pc: RTCPeerConnection;
    try {
      pc = this.opts.webrtcFactory();
    } catch (err) {
      const e =
        err instanceof Error && err.name === "SdkError"
          ? (err as SdkError)
          : sdkError("no_webrtc_impl", `webrtcFactory threw: ${String(err)}`, err);
      this.fail(e);
      throw e;
    }
    this.pc = pc;
    pc.onconnectionstatechange = (): void => {
      switch (pc.connectionState) {
        case "connected":
          this.opts.onSessionConnected();
          break;
        case "failed":
          this.fail(sdkError("ice_failed", "WebRTC connectionState=failed"));
          break;
        case "closed":
          // Treated as a normal close when initiated by `endSession()`.
          break;
        default:
        // 'new' | 'connecting' | 'disconnected' — no action.
      }
    };
    pc.oniceconnectionstatechange = (): void => {
      if (pc.iceConnectionState === "failed") {
        this.fail(sdkError("ice_failed", "ICE connection failed"));
      }
    };
    pc.ontrack = (ev: RTCTrackEvent): void => {
      const stream = ev.streams[0] ?? new MediaStream([ev.track]);
      this.attachRemoteStream(stream);
    };

    // Acquire mic and attach.
    try {
      this.localStream = await (this.opts.getUserMediaFn ?? defaultGetUserMedia)({
        audio: this.opts.micConstraints,
      });
    } catch (err) {
      const e =
        err instanceof Error && err.name === "NotAllowedError"
          ? sdkError("permission_denied", "Microphone permission denied")
          : sdkError("no_microphone_api", `getUserMedia failed: ${String(err)}`, err);
      this.fail(e);
      throw e;
    }
    for (const track of this.localStream.getAudioTracks()) {
      pc.addTrack(track, this.localStream);
    }

    // Build sink BEFORE the answer arrives so a fast remote can attach.
    try {
      this.sink = this.opts.audioSinkFactory();
    } catch (err) {
      const e =
        err instanceof Error && err.name === "SdkError"
          ? (err as SdkError)
          : sdkError("no_microphone_api", `audioSinkFactory threw: ${String(err)}`, err);
      this.fail(e);
      throw e;
    }

    // Create + set offer.
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    // Full-gather then offer (R-7).
    try {
      await waitForIceGatheringComplete(pc, this.opts.iceGatherTimeoutMs ?? 5_000);
    } catch (err) {
      const e =
        err instanceof Error && err.name === "SdkError"
          ? (err as SdkError)
          : sdkError("ice_gathering_timeout", String(err), err);
      this.fail(e);
      throw e;
    }

    // POST offer.
    const sdp = pc.localDescription?.sdp ?? "";
    let answer;
    try {
      answer = await this.signaling.postOffer({ deviceId: this.opts.deviceId, sdp });
    } catch (err) {
      const e =
        err instanceof Error && err.name === "SdkError"
          ? (err as SdkError)
          : sdkError("signaling_failed", String(err), err);
      this.fail(e);
      throw e;
    }
    this.resolvedSessionId = answer.session_id;
    await pc.setRemoteDescription({ type: "answer", sdp: answer.sdp });

    // Emit session_started now that the offer/answer is complete. The
    // ended promise stays unresolved until close()/fail().
    this.opts.bus.emit("session_started", this.publicHandle());
  }

  /** Public handle exposed to consumers. */
  publicHandle(): VoiceSessionPublic {
    return {
      sessionId: this.resolvedSessionId,
      startedAt: this.startedAt,
      ended: this.ended,
    };
  }

  /**
   * Enable/disable the outbound mic track without tearing down the PC.
   *
   * Use for PTT-style UX: build the session once on connect/adopt, mute
   * by default, unmute on press and mute on release. This matches the
   * legacy electron-test's behaviour and avoids creating a new PC per
   * utterance (which races the gateway-side silence detector — the
   * detector needs ~3 s of silence after speech to trigger STT, so a
   * mouseup that tears down the PC inside that window means STT never
   * fires).
   *
   * No-op if the session has no local stream yet. Idempotent.
   */
  setMicEnabled(enabled: boolean): void {
    if (!this.localStream) return;
    for (const track of this.localStream.getAudioTracks()) {
      track.enabled = enabled;
    }
  }

  /** Caller-initiated close. */
  close(reason: VoiceSessionResult["reason"] = "operator_ended"): void {
    if (!this.active) return;
    this.active = false;
    if (this.pc) {
      try {
        this.pc.close();
      } catch {
        // pc.close() never throws per spec but be defensive.
      }
      this.pc = null;
    }
    if (this.localStream) {
      for (const track of this.localStream.getTracks()) {
        try {
          track.stop();
        } catch {
          // Best-effort.
        }
      }
      this.localStream = null;
    }
    if (this.sink) {
      try {
        this.sink.detach();
      } catch {
        // Best-effort.
      }
      this.sink = null;
    }
    const result: VoiceSessionResult = {
      endedAt: Date.now(),
      turnCount: this.turnCount,
      reason,
    };
    this.opts.bus.emit("session_ended", result);
    this.opts.onSessionEnded(reason);
    this.endedResolve(result);
  }

  // -------- internal --------------------------------------------------

  private attachRemoteStream(stream: MediaStream): void {
    if (this.sink) {
      try {
        this.sink.attach(stream);
      } catch (err) {
        this.opts.bus.emit("transient_error", {
          code: "ice_retry",
          message: `audio sink attach failed: ${String(err)}`,
          retryInMs: 0,
          attempt: 1,
        });
      }
    }
    this.opts.bus.emit("remote_stream", { stream });
    if (!this.gotFirstRemoteAudio) {
      this.gotFirstRemoteAudio = true;
      this.turnCount += 1;
      this.opts.onFirstRemoteAudio();
    }
  }

  private fail(error: SdkError): void {
    if (!this.active) return;
    this.opts.bus.emit("error", error);
    const reason: VoiceSessionResult["reason"] =
      error.code === "ice_failed"
        ? "ice_failed"
        : error.code === "ws_disconnected"
          ? "ws_disconnected"
          : "fatal_error";
    this.opts.onSessionEnded(reason, error);
    this.active = false;
    if (this.pc) {
      try {
        this.pc.close();
      } catch {
        // Best-effort.
      }
      this.pc = null;
    }
    if (this.localStream) {
      for (const track of this.localStream.getTracks()) {
        try {
          track.stop();
        } catch {
          // Best-effort.
        }
      }
      this.localStream = null;
    }
    if (this.sink) {
      try {
        this.sink.detach();
      } catch {
        // Best-effort.
      }
      this.sink = null;
    }
    const result: VoiceSessionResult = {
      endedAt: Date.now(),
      turnCount: this.turnCount,
      reason,
      error,
    };
    this.opts.bus.emit("session_ended", result);
    this.endedResolve(result);
  }
}
