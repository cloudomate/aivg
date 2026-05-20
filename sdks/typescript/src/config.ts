/**
 * SatelliteConfig HTTP client + WS `config_changed` subscriber (US2).
 *
 * Per contracts/wire-protocol.md "HTTP shapes":
 *  - GET  /satellite/{id}/config         → ConfigGetResponse
 *  - POST /satellite/{id}/config         → ConfigPostResponse (or 409 → ConfigConflictResponse)
 *
 * Wire is snake_case; SDK surface is camelCase. This module owns the
 * mapping in both directions.
 */

import { sdkError } from "./errors";
import type { SatelliteConfig as SatelliteConfigPublic } from "./events";
import type {
  ConfigGetResponse,
  ConfigPostRequest,
  ConfigPostResponse,
  ConfigConflictResponse,
} from "./proto/rest-shapes";
import type { SatelliteConfigWire } from "./proto/ws-messages";

export interface ConfigClientOptions {
  gatewayUrl: string;
  deviceId: string;
  fetchFn?: typeof fetch;
  /** Hard timeout for HTTP exchanges. Default 10 000 ms. */
  timeoutMs?: number;
}

/** Public-facing 409 error subclass — carries `currentVersion` so consumer can retry. */
export class ConfigVersionConflict extends Error {
  public readonly code = "version_conflict" as const;
  constructor(public readonly currentVersion: number) {
    super(`config version conflict — gateway is at version ${currentVersion}`);
    this.name = "ConfigVersionConflict";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class ConfigClient {
  private readonly base: string;
  private readonly deviceId: string;
  private readonly fetchFn: typeof fetch;
  private readonly timeoutMs: number;
  /** Last known config — used for optimistic concurrency on partial updates. */
  private cached: SatelliteConfigPublic | null = null;

  constructor(opts: ConfigClientOptions) {
    this.base = opts.gatewayUrl.replace(/\/+$/, "");
    this.deviceId = opts.deviceId;
    this.fetchFn = opts.fetchFn ?? globalThis.fetch.bind(globalThis);
    this.timeoutMs = opts.timeoutMs ?? 10_000;
  }

  /** Wire `snake_case` → public `camelCase`. */
  static wireToPublic(w: SatelliteConfigWire): SatelliteConfigPublic {
    return {
      wakeWord: w.wake_word,
      routingMode: w.routing_mode,
      logLevel: w.log_level.toLowerCase() as SatelliteConfigPublic["logLevel"],
      heartbeatInterval: w.heartbeat_interval,
      extra: w.extra,
      version: w.version,
    };
  }

  /** Public `camelCase` partial → wire `snake_case` partial. */
  static publicPatchToWire(
    p: Partial<SatelliteConfigPublic>,
  ): Partial<Omit<SatelliteConfigWire, "version">> {
    const out: Partial<Omit<SatelliteConfigWire, "version">> = {};
    if (p.wakeWord !== undefined) out.wake_word = p.wakeWord;
    if (p.routingMode !== undefined) out.routing_mode = p.routingMode;
    if (p.logLevel !== undefined) {
      out.log_level = p.logLevel.toUpperCase() as SatelliteConfigWire["log_level"];
    }
    if (p.heartbeatInterval !== undefined) out.heartbeat_interval = p.heartbeatInterval;
    if (p.extra !== undefined) out.extra = p.extra;
    return out;
  }

  /** Update local cache from an inbound `config_changed` WS event. */
  cacheChanged(cfg: SatelliteConfigPublic): void {
    this.cached = cfg;
  }

  async get(): Promise<SatelliteConfigPublic> {
    const ctrl = new AbortController();
    const handle = setTimeout(() => { ctrl.abort(); }, this.timeoutMs);
    let resp: Response;
    try {
      resp = await this.fetchFn(`${this.base}/satellite/${this.deviceId}/config`, {
        method: "GET",
        signal: ctrl.signal,
      });
    } catch (err) {
      throw sdkError("signaling_failed", `GET config failed: ${String(err)}`, err);
    } finally {
      clearTimeout(handle);
    }
    if (!resp.ok) {
      throw sdkError(
        "signaling_failed",
        `GET config → HTTP ${resp.status} ${resp.statusText}`,
      );
    }
    const wire = (await resp.json()) as ConfigGetResponse;
    const out = ConfigClient.wireToPublic(wire);
    this.cached = out;
    return out;
  }

  async patch(patch: Partial<SatelliteConfigPublic>): Promise<SatelliteConfigPublic> {
    // Optimistic concurrency: require knowledge of current version.
    const baseVersion = patch.version ?? this.cached?.version;
    if (baseVersion === undefined) {
      // Fetch first so we have a version to send.
      const current = await this.get();
      return this.patchWithVersion(patch, current.version);
    }
    return this.patchWithVersion(patch, baseVersion);
  }

  private async patchWithVersion(
    patch: Partial<SatelliteConfigPublic>,
    baseVersion: number,
  ): Promise<SatelliteConfigPublic> {
    const body: ConfigPostRequest = {
      patch: ConfigClient.publicPatchToWire(patch),
      if_match_version: baseVersion,
    };
    const ctrl = new AbortController();
    const handle = setTimeout(() => { ctrl.abort(); }, this.timeoutMs);
    let resp: Response;
    try {
      resp = await this.fetchFn(`${this.base}/satellite/${this.deviceId}/config`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });
    } catch (err) {
      throw sdkError("signaling_failed", `POST config failed: ${String(err)}`, err);
    } finally {
      clearTimeout(handle);
    }
    if (resp.status === 409) {
      // Optimistic concurrency conflict — typed error so consumer can refresh + retry.
      const conflict = (await resp.json()) as ConfigConflictResponse;
      throw new ConfigVersionConflict(conflict.error.current_version);
    }
    if (!resp.ok) {
      throw sdkError(
        "signaling_failed",
        `POST config → HTTP ${resp.status} ${resp.statusText}`,
      );
    }
    const wire = (await resp.json()) as ConfigPostResponse;
    const out = ConfigClient.wireToPublic(wire);
    this.cached = out;
    return out;
  }
}
