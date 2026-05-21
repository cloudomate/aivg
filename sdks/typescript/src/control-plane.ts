/**
 * Long-lived control-plane WebSocket client.
 *
 * Owns: ws://<gateway>/satellite/ws?device_id=<id>
 *   - sends `register` immediately on connect
 *   - sends `heartbeat` every heartbeatIntervalMs
 *   - parses inbound messages via parseWsInbound() and emits to the bus
 *   - reconnect with exponential back-off + ±20 % jitter per R-6
 *
 * Per constitution Principle III: durable traffic stays on the WS. The
 * WS is independent of any voice session and stays up across calls.
 */

import { CONTRACT_VERSION } from "./proto/version";
import { parseWsInbound, type WsOutboundMessage } from "./proto/ws-messages";
import type { EventBus, SatelliteEvents } from "./events";
import type { SatelliteState } from "./state";
import { sdkError, type SdkError } from "./errors";
import { AgentEventDispatcher } from "./agent-events";

export interface ReconnectPolicy {
  initialMs: number;
  factor: number;
  maxMs: number;
  /** ±jitter, e.g. 0.2 = ±20 %. */
  jitter: number;
  /** Stable-for-this-long resets the back-off to initialMs. */
  resetAfterMs: number;
  maxRetries?: number;
}

export const DEFAULT_RECONNECT_POLICY: ReconnectPolicy = {
  initialMs: 500,
  factor: 1.5,
  maxMs: 30_000,
  jitter: 0.2,
  resetAfterMs: 60_000,
};

/**
 * Anything shaped like the WHATWG WebSocket. Injected so unit tests can
 * pass a fake without the SDK's transport behaviour depending on
 * globals at module-load time.
 */
export interface WebSocketLike {
  send(data: string): void;
  close(code?: number, reason?: string): void;
  readonly readyState: number;
  onopen: ((this: WebSocketLike, ev: Event) => void) | null;
  onclose: ((this: WebSocketLike, ev: CloseEvent) => void) | null;
  onerror: ((this: WebSocketLike, ev: Event) => void) | null;
  onmessage: ((this: WebSocketLike, ev: MessageEvent<string>) => void) | null;
}

export type WebSocketFactory = (url: string) => WebSocketLike;

const OPEN_STATE = 1;

export interface ControlPlaneOptions {
  gatewayUrl: string;
  deviceId: string;
  bus: EventBus<SatelliteEvents>;
  /** Required getter — control plane reads current FSM state on every heartbeat. */
  getState: () => SatelliteState;
  firmwareVersion: string;
  /** Default 30 000. */
  heartbeatIntervalMs?: number;
  reconnectPolicy?: ReconnectPolicy;
  wsFactory?: WebSocketFactory;
  /** Process-time clock — overridable for fake-timer tests. */
  now?: () => number;
  /** Setter for delayed work — overridable for fake-timer tests. */
  setTimeoutFn?: (cb: () => void, ms: number) => ReturnType<typeof setTimeout>;
  clearTimeoutFn?: (handle: ReturnType<typeof setTimeout>) => void;
  setIntervalFn?: (cb: () => void, ms: number) => ReturnType<typeof setInterval>;
  clearIntervalFn?: (handle: ReturnType<typeof setInterval>) => void;
}

const defaultWsFactory: WebSocketFactory = (url) => {
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
  if (typeof globalThis.WebSocket !== "function") {
    throw sdkError(
      "ws_disconnected",
      "No global WebSocket constructor available in this runtime",
    );
  }
  return new globalThis.WebSocket(url) as unknown as WebSocketLike;
};

/**
 * Compute jittered back-off for attempt N (1-based) given the policy.
 * Exported so reconnect-backoff.test.ts can assert the schedule.
 */
export function computeBackoff(
  policy: ReconnectPolicy,
  attempt: number,
  rng: () => number = Math.random,
): number {
  if (attempt < 1) attempt = 1;
  const raw = Math.min(policy.maxMs, policy.initialMs * policy.factor ** (attempt - 1));
  // ±jitter
  const j = policy.jitter;
  const lo = 1 - j;
  const hi = 1 + j;
  const factor = lo + rng() * (hi - lo);
  return Math.max(0, Math.round(raw * factor));
}

/**
 * Build the WS URL from a gateway base. `https://x` → `wss://x/satellite/ws?…`;
 * `http://x` → `ws://x/satellite/ws?…`. Strips trailing slashes.
 */
export function buildWsUrl(gatewayUrl: string, deviceId: string): string {
  const u = new URL(gatewayUrl);
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  u.pathname = u.pathname.replace(/\/+$/, "") + "/satellite/ws";
  u.searchParams.set("device_id", deviceId);
  return u.toString();
}

/** Internal connection states. Distinct from SatelliteState. */
type CpStatus = "idle" | "connecting" | "open" | "backoff" | "closed";

export class ControlPlane {
  private readonly opts: Required<
    Omit<ControlPlaneOptions, "reconnectPolicy" | "heartbeatIntervalMs">
  > & {
    reconnectPolicy: ReconnectPolicy;
    heartbeatIntervalMs: number;
  };
  private ws: WebSocketLike | null = null;
  private status: CpStatus = "idle";
  private attempt = 0;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private lastOpenedAt = 0;
  private stoppedByUser = false;
  private readonly agentDispatch: AgentEventDispatcher = new AgentEventDispatcher();
  /**
   * Resolved on first successful `open`+register; rejected on permanent
   * failure (max-retries exceeded). Re-created on `start()`.
   */
  private firstConnectedDeferred: {
    resolve: () => void;
    reject: (e: SdkError) => void;
  } | null = null;
  private firstConnectedPromise: Promise<void> | null = null;

  constructor(options: ControlPlaneOptions) {
    this.opts = {
      gatewayUrl: options.gatewayUrl,
      deviceId: options.deviceId,
      bus: options.bus,
      getState: options.getState,
      firmwareVersion: options.firmwareVersion,
      heartbeatIntervalMs: options.heartbeatIntervalMs ?? 30_000,
      reconnectPolicy: options.reconnectPolicy ?? DEFAULT_RECONNECT_POLICY,
      wsFactory: options.wsFactory ?? defaultWsFactory,
      now: options.now ?? (() => Date.now()),
      // Wrap timer host functions: in a browser/Electron renderer these
      // are window methods and lose their `this` binding when assigned
      // as bare references — calling them then throws "Illegal invocation".
      setTimeoutFn: options.setTimeoutFn ?? ((cb, ms) => setTimeout(cb, ms)),
      clearTimeoutFn: options.clearTimeoutFn ?? ((h) => clearTimeout(h)),
      setIntervalFn: options.setIntervalFn ?? ((cb, ms) => setInterval(cb, ms)),
      clearIntervalFn: options.clearIntervalFn ?? ((h) => clearInterval(h)),
    };
  }

  /** Open the WS + send `register`. Resolves on first successful registration. */
  start(): Promise<void> {
    if (this.firstConnectedPromise) return this.firstConnectedPromise;
    this.stoppedByUser = false;
    this.firstConnectedPromise = new Promise<void>((resolve, reject) => {
      this.firstConnectedDeferred = { resolve, reject };
    });
    this.connect();
    return this.firstConnectedPromise;
  }

  /** Close the WS, cancel timers, do not reconnect. */
  stop(): void {
    this.stoppedByUser = true;
    if (this.reconnectTimer !== null) {
      this.opts.clearTimeoutFn(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.heartbeatTimer !== null) {
      this.opts.clearIntervalFn(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    if (this.ws) {
      this.ws.close(1000, "client_disconnect");
      this.ws = null;
    }
    this.status = "closed";
  }

  /** Send any outbound message (register, heartbeat, command_result). */
  send(msg: WsOutboundMessage): void {
    if (!this.ws || this.ws.readyState !== OPEN_STATE) return;
    this.ws.send(JSON.stringify(msg));
  }

  isOpen(): boolean {
    return this.ws?.readyState === OPEN_STATE;
  }

  // -------- internal --------------------------------------------------

  private connect(): void {
    this.status = "connecting";
    const url = buildWsUrl(this.opts.gatewayUrl, this.opts.deviceId);
    let ws: WebSocketLike;
    try {
      ws = this.opts.wsFactory(url);
    } catch (err) {
      this.handleConnectionFailure(err);
      return;
    }
    this.ws = ws;
    ws.onopen = (): void => { this.handleOpen(); };
    ws.onclose = (ev: CloseEvent): void => { this.handleClose(ev); };
    ws.onerror = (): void => {
      // onerror → onclose usually follows; surface as transient.
      this.opts.bus.emit("transient_error", {
        code: "ws_disconnected",
        message: "WebSocket error",
        retryInMs: 0,
        attempt: this.attempt,
      });
    };
    ws.onmessage = (ev: MessageEvent<string>): void => { this.handleMessage(ev.data); };
  }

  private handleOpen(): void {
    this.status = "open";
    this.lastOpenedAt = this.opts.now();
    // Do NOT reset `attempt` here — exponential back-off depends on the
    // counter persisting across short reconnect cycles. The reset only
    // happens in handleClose() after `resetAfterMs` of stability (R-6).
    // Send `register` immediately.
    this.send({
      type: "register",
      device_id: this.opts.deviceId,
      contract_version: CONTRACT_VERSION,
    });
    // Start heartbeat.
    if (this.heartbeatTimer !== null) {
      this.opts.clearIntervalFn(this.heartbeatTimer);
    }
    const startedAt = this.opts.now();
    this.heartbeatTimer = this.opts.setIntervalFn(() => {
      this.send({
        type: "heartbeat",
        device_id: this.opts.deviceId,
        state: this.opts.getState(),
        uptime_s: (this.opts.now() - startedAt) / 1000,
        firmware_version: this.opts.firmwareVersion,
      });
    }, this.opts.heartbeatIntervalMs);
    // Resolve first-connected promise on the very first open.
    this.firstConnectedDeferred?.resolve();
    this.firstConnectedDeferred = null;
  }

  private handleClose(_ev: CloseEvent): void {
    if (this.heartbeatTimer !== null) {
      this.opts.clearIntervalFn(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    this.ws = null;
    if (this.stoppedByUser) {
      this.status = "closed";
      return;
    }
    // If we stayed open long enough, reset back-off.
    const stableMs = this.opts.now() - this.lastOpenedAt;
    if (stableMs >= this.opts.reconnectPolicy.resetAfterMs) {
      this.attempt = 0;
    }
    this.scheduleReconnect();
  }

  private handleConnectionFailure(err: unknown): void {
    this.opts.bus.emit("transient_error", {
      code: "ws_disconnected",
      message: `WebSocket factory threw: ${String(err)}`,
      retryInMs: 0,
      attempt: this.attempt,
    });
    this.scheduleReconnect();
  }

  private scheduleReconnect(): void {
    if (this.stoppedByUser) return;
    const policy = this.opts.reconnectPolicy;
    this.attempt += 1;
    if (policy.maxRetries !== undefined && this.attempt > policy.maxRetries) {
      const e = sdkError(
        "ws_max_retries_exceeded",
        `gave up after ${policy.maxRetries} reconnect attempts`,
      );
      this.opts.bus.emit("error", e);
      this.firstConnectedDeferred?.reject(e);
      this.firstConnectedDeferred = null;
      this.status = "closed";
      return;
    }
    const delay = computeBackoff(policy, this.attempt);
    this.opts.bus.emit("transient_error", {
      code: "ws_disconnected",
      message: `reconnecting in ${delay}ms`,
      retryInMs: delay,
      attempt: this.attempt,
    });
    this.status = "backoff";
    this.reconnectTimer = this.opts.setTimeoutFn(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  private handleMessage(raw: string): void {
    const msg = parseWsInbound(raw);
    switch (msg.type) {
      case "registered":
        // Gateway's reply to our outbound `register` message. The
        // `adoption_state` field is the FIRST adoption signal we see;
        // surface it as an `adoption` bus event so US2's
        // AdoptionTracker can decorate with firstApproval semantics.
        this.opts.bus.emit("adoption", {
          state: msg.adoption_state,
          firstApproval: false, // AdoptionTracker re-emits with the right flag
        });
        return;
      case "state_update":
        // Broadcast to EVERY connected WS — filter to our own device_id.
        // Other devices' state changes are not our consumer's concern.
        if (msg.device_id !== this.opts.deviceId) return;
        this.opts.bus.emit("adoption", {
          state: msg.adoption_state,
          firstApproval: false,
        });
        return;
      // The rest of the message types are handled by US2/US3-side
      // modules that subscribe to the bus directly. The control plane
      // is concerned with the WS *transport*, not the message *meaning*.
      // We still need to surface them so subscribers can react:
      case "config_changed":
        // Broadcast to all WS subscribers — filter to our device_id.
        if (msg.device_id !== this.opts.deviceId) return;
        // Map snake_case wire → camelCase SDK shape. The gateway sends
        // `config_version` as a SIBLING (not inside config) — flatten
        // here so the public SatelliteConfig keeps the `version` field
        // it has always had.
        this.opts.bus.emit("config_changed", {
          wakeWord: msg.config.wake_word,
          routingMode: msg.config.routing_mode,
          logLevel: msg.config.log_level.toLowerCase() as
            | "debug"
            | "info"
            | "warn"
            | "error",
          heartbeatInterval: msg.config.heartbeat_interval,
          extra: msg.config.extra ?? {},
          version: msg.config_version ?? msg.config.version ?? 0,
        });
        return;
      case "command":
        // The reply channel + verb dispatch land in US2 (T042). For
        // Phase 3 we surface the event so a smoke test can verify
        // the wire path works.
        this.opts.bus.emit("command", {
          verb: msg.verb,
          args: msg.args,
          reply: (result) => {
            this.send({
              type: "command_result",
              request_id: msg.request_id,
              ok: result.ok,
              ...(result.message !== undefined ? { message: result.message } : {}),
              ...(result.data !== undefined ? { data: result.data } : {}),
            });
          },
        });
        return;
      case "log_entry":
        this.opts.bus.emit("log", msg.entry);
        return;
      case "ota_manifest":
        this.opts.bus.emit("ota_manifest", {
          version: msg.manifest.version,
          url: msg.manifest.url,
          ...(msg.manifest.sha256 !== undefined ? { sha256: msg.manifest.sha256 } : {}),
          manifestId: msg.manifest.manifest_id,
          ...(msg.manifest.apply_by !== undefined ? { applyBy: msg.manifest.apply_by } : {}),
        });
        return;
      case "ota_progress":
        this.opts.bus.emit("ota_progress", {
          manifestId: msg.manifest_id,
          state: msg.state,
          ...(msg.progress !== undefined ? { progress: msg.progress } : {}),
          ...(msg.message !== undefined ? { message: msg.message } : {}),
        });
        return;
      case "agent_event":
        // US3 fan-out: route into tool_call / skill / transcript
        // typed events based on `kind`. Unknown `kind` values emit
        // one transient_error per session per R-8.
        this.agentDispatch.dispatch(this.opts.bus, msg);
        return;
      case "state":
        // Gateway voice-session state (idle/listening/thinking/speaking/...)
        // — broadcast per-session UI signal. Don't conflate with the SDK's
        // local FSM `state` event; surface as its own typed event.
        this.opts.bus.emit("gateway_state", {
          state: msg.state,
          ...(msg.session_id !== undefined ? { sessionId: msg.session_id } : {}),
        });
        return;
      case "partial_transcript":
        // Live ASR — surface as a non-final transcript delta on the
        // existing transcript event so chat-style UIs receive both
        // legacy live ASR and US3-style agent transcript deltas via
        // the same listener.
        this.opts.bus.emit("transcript", {
          speaker: "user",
          text: msg.text,
          final: false,
          seq: 0,
          ts: Date.now() / 1000,
        });
        return;
      case "barge_in":
        this.opts.bus.emit("barge_in", {
          ...(msg.session_id !== undefined ? { sessionId: msg.session_id } : {}),
        });
        return;
      default:
        // Unknown / parse-error sentinels. Forward-compat per R-8.
        this.opts.bus.emit("transient_error", {
          code: "signaling_retry",
          message: `unknown WS message type: ${msg.type}`,
          retryInMs: 0,
          attempt: 1,
        });
    }
  }
}
