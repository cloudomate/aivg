/**
 * `Satellite` — the top-level handle a consumer application instantiates.
 *
 * Binding contract: `specs/014-aivg-sat-sdk-ts/contracts/satellite-api.md`.
 *
 * Owns:
 *  - device identity (deviceId, deviceName, deviceType, firmwareVersion)
 *  - the long-lived control-plane WebSocket (via ControlPlane)
 *  - the per-session WebRTC PeerConnection (via VoiceSession)
 *  - the typed event bus
 *  - the lifecycle FSM
 *
 * Construction is side-effect-free. All side effects happen at
 * `connect()` (opens WS) and `beginSession()` (asks for mic, opens PC).
 */

import { ControlPlane, type ControlPlaneOptions } from "./control-plane";
import { InternalVoiceSession } from "./voice-session";
import { transition, type SatelliteState } from "./state";
import { sdkError } from "./errors";
import { EventBus, iterate } from "./events";
import type {
  SatelliteEvents,
  LogEntry,
  SatelliteConfig,
  VoiceSession,
  AdoptionEvent,
} from "./events";
import type { WebrtcFactory, AudioSinkFactory } from "./webrtc/injectable";
import { defaultWebrtcFactory } from "./webrtc/browser";
import { defaultAudioSinkFactory } from "./webrtc/audio-sink";
import { AdoptionTracker } from "./adoption";
// ConfigVersionConflict is exported from src/index.ts barrel and referenced
// from JSDoc in setConfig() — re-imported here keeps the consumer-visible
// docstring's `@throws` claim accurate.
import { ConfigClient } from "./config";

export interface ReconnectPolicy {
  initialMs: number;
  factor: number;
  maxMs: number;
  jitter: number;
  resetAfterMs: number;
  maxRetries?: number;
}

export interface SatelliteOptions {
  gatewayUrl: string;
  deviceId: string;
  deviceName?: string;
  deviceType: "browser" | "electron" | "node" | "rpi" | "esp32" | "custom";
  firmwareVersion?: string;

  // DI holes (R-1, R-9). Defaults provided for browser/Electron;
  // Node consumers MUST inject.
  webrtcFactory?: WebrtcFactory;
  audioSinkFactory?: AudioSinkFactory;
  micConstraints?: MediaTrackConstraints;

  heartbeatIntervalMs?: number;
  reconnectPolicy?: ReconnectPolicy;
}

const DEFAULT_MIC_CONSTRAINTS: MediaTrackConstraints = {
  echoCancellation: true,
  noiseSuppression: true,
  autoGainControl: true,
};

type Unsubscribe = () => void;

export class Satellite {
  public readonly options: Readonly<Required<Pick<SatelliteOptions, "gatewayUrl" | "deviceId" | "deviceType">> & SatelliteOptions>;

  private readonly bus = new EventBus<SatelliteEvents>();
  private readonly cp: ControlPlane;
  private readonly adoption: AdoptionTracker = new AdoptionTracker();
  private readonly configClient: ConfigClient;
  private currentState: SatelliteState = "idle";
  private currentSession: InternalVoiceSession | null = null;
  private connectPromise: Promise<void> | null = null;
  private beginPromise: Promise<VoiceSession> | null = null;
  /** Mixed-content sanity-check result (set once at construction). */
  private readonly mixedContentError: ReturnType<typeof sdkError> | null;

  constructor(options: SatelliteOptions) {
    // Normalise + freeze options.
    const opts: SatelliteOptions = { ...options };
    this.options = Object.freeze(opts) as typeof this.options;
    this.mixedContentError = checkMixedContent(opts.gatewayUrl);

    // Attach adoption tracker BEFORE the control plane subscribes so
    // its re-emit lands at the top of the listener queue and consumers
    // see the correct `firstApproval` flag.
    this.adoption.attach(this.bus);

    // Cache config from inbound `config_changed` events so optimistic
    // concurrency on setConfig() works without an extra GET round-trip.
    this.bus.on("config_changed", (cfg) => {
      this.configClient.cacheChanged(cfg);
    });

    // Configure HTTP config client.
    this.configClient = new ConfigClient({
      gatewayUrl: opts.gatewayUrl,
      deviceId: opts.deviceId,
    });

    // Construct the control plane wiring.
    const cpOpts: ControlPlaneOptions = {
      gatewayUrl: opts.gatewayUrl,
      deviceId: opts.deviceId,
      bus: this.bus,
      getState: () => this.currentState,
      firmwareVersion: opts.firmwareVersion ?? "0.0.0",
    };
    if (opts.heartbeatIntervalMs !== undefined) {
      cpOpts.heartbeatIntervalMs = opts.heartbeatIntervalMs;
    }
    if (opts.reconnectPolicy !== undefined) {
      cpOpts.reconnectPolicy = opts.reconnectPolicy;
    }
    this.cp = new ControlPlane(cpOpts);
  }

  // -------- public state read-out --------

  get state(): SatelliteState {
    return this.currentState;
  }

  get isAdopted(): boolean {
    return this.adoption.state === "adopted";
  }

  get adoptionState(): AdoptionEvent["state"] {
    return this.adoption.state;
  }

  // -------- event surface --------

  on<E extends keyof SatelliteEvents>(
    event: E,
    handler: (payload: SatelliteEvents[E]) => void,
  ): Unsubscribe {
    return this.bus.on(event, handler);
  }

  off<E extends keyof SatelliteEvents>(
    event: E,
    handler: (payload: SatelliteEvents[E]) => void,
  ): void {
    this.bus.off(event, handler);
  }

  transcripts(): AsyncIterableIterator<SatelliteEvents["transcript"]> {
    return iterate(this.bus, "transcript");
  }
  logs(): AsyncIterableIterator<LogEntry> {
    return iterate(this.bus, "log");
  }
  states(): AsyncIterableIterator<SatelliteState> {
    // states() yields just the `current` half of the StateChangePayload.
    const inner = iterate(this.bus, "state");
    const outer: AsyncIterableIterator<SatelliteState> = {
      [Symbol.asyncIterator](): AsyncIterableIterator<SatelliteState> {
        return outer;
      },
      async next(): Promise<IteratorResult<SatelliteState>> {
        const r = await inner.next();
        if (r.done) return { value: undefined as never, done: true };
        return { value: r.value.current, done: false };
      },
      async return(): Promise<IteratorResult<SatelliteState>> {
        await inner.return!();
        return { value: undefined as never, done: true };
      },
    };
    return outer;
  }

  // -------- lifecycle --------

  /** Open the control plane WS, register, stay connected. Idempotent. */
  connect(): Promise<void> {
    if (this.mixedContentError !== null) {
      return Promise.reject(this.mixedContentError);
    }
    if (this.connectPromise) return this.connectPromise;
    this.connectPromise = this.cp.start();
    return this.connectPromise;
  }

  /** Close the WS + any in-flight session. Always succeeds. */
  disconnect(): Promise<void> {
    if (this.currentSession) {
      this.currentSession.close("operator_ended");
      this.currentSession = null;
    }
    this.cp.stop();
    this.connectPromise = null;
    return Promise.resolve();
  }

  /** Begin a voice session (idempotent). */
  beginSession(): Promise<VoiceSession> {
    if (this.beginPromise) return this.beginPromise;
    if (this.currentSession) {
      return Promise.resolve(this.currentSession.publicHandle());
    }
    if (!this.adoption.hasBeenAdopted && this.adoption.state !== "adopted") {
      // Spec edge case: `not_adopted` short-circuit per FR-001.
      return Promise.reject(
        sdkError("not_adopted", "Device is not adopted yet — operator must approve via `aivg device adopt`"),
      );
    }
    const session = new InternalVoiceSession({
      gatewayUrl: this.options.gatewayUrl,
      deviceId: this.options.deviceId,
      bus: this.bus,
      webrtcFactory: this.options.webrtcFactory ?? defaultWebrtcFactory,
      audioSinkFactory: this.options.audioSinkFactory ?? defaultAudioSinkFactory,
      micConstraints: this.options.micConstraints ?? DEFAULT_MIC_CONSTRAINTS,
      onSessionConnected: () => { this.driveFsm({ kind: "begin_session_resolved" }); },
      onFirstRemoteAudio: () => { this.driveFsm({ kind: "first_remote_audio" }); },
      onSessionEnded: () => {
        this.currentSession = null;
        this.driveFsm({ kind: "session_ended" });
      },
    });
    this.currentSession = session;
    this.beginPromise = session
      .start()
      .then(() => session.publicHandle())
      .finally(() => {
        this.beginPromise = null;
      });
    return this.beginPromise;
  }

  /** End the active session. Returns once resources are released. */
  endSession(): Promise<void> {
    const s = this.currentSession;
    if (!s) return Promise.resolve();
    s.close("operator_ended");
    this.currentSession = null;
    this.driveFsm({ kind: "end_session_resolved" });
    return Promise.resolve();
  }

  /** Recover from fatal `error` state back to `idle`. */
  recover(): void {
    this.driveFsm({ kind: "recover" });
  }

  // -------- US2: config push/pull -----------------------------------

  /** Read the current SatelliteConfig from the gateway. */
  getConfig(): Promise<SatelliteConfig> {
    return this.configClient.get();
  }

  /**
   * Push a partial config update to the gateway. Throws
   * `ConfigVersionConflict` if the local cached version is stale — the
   * consumer should refresh via `getConfig()` and retry.
   */
  setConfig(patch: Partial<SatelliteConfig>): Promise<SatelliteConfig> {
    return this.configClient.patch(patch);
  }

  // -------- internal --------

  private driveFsm(event: Parameters<typeof transition>[1]): void {
    const previous = this.currentState;
    const current = transition(previous, event);
    if (previous !== current) {
      this.currentState = current;
      this.bus.emit("state", { previous, current });
    }
  }
}

/**
 * Detect a `https://` consumer page trying to talk to an `http://` gateway.
 * Returns a typed error if so (browser will block the upgrade anyway, but
 * the SDK surfaces a clearer code).
 */
function checkMixedContent(gatewayUrl: string): ReturnType<typeof sdkError> | null {
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
  if (typeof window === "undefined" || !window.location) return null;
  if (window.location.protocol !== "https:") return null;
  let u: URL;
  try {
    u = new URL(gatewayUrl);
  } catch {
    return null;
  }
  if (u.protocol === "http:" && u.hostname !== "localhost" && u.hostname !== "127.0.0.1") {
    return sdkError(
      "mixed_content",
      `Page is https: but gatewayUrl is http://${u.host} — use HTTPS gateway or develop on localhost`,
    );
  }
  return null;
}
