/**
 * OTA forwarding helpers (US3 / FR-018).
 *
 * The control-plane already maps inbound `ota_manifest` and
 * `ota_progress` WS messages onto the bus. This module provides:
 *
 *   - typed accessors for consumers parsing OtaManifest details
 *   - the `applyByExpired()` helper for honoring deadline hints
 *
 * Per FR-018: the SDK NEVER auto-applies an OTA. It forwards the
 * manifest to the consumer and lets the host (browser / Electron app)
 * decide what "apply" means.
 */

import type { OtaManifest } from "./events";

export type { OtaManifest, OtaProgress } from "./events";

/** True if the manifest's `applyBy` (ISO-8601) is in the past. */
export function applyByExpired(manifest: OtaManifest, now: number = Date.now()): boolean {
  if (manifest.applyBy === undefined) return false;
  const deadline = Date.parse(manifest.applyBy);
  if (Number.isNaN(deadline)) return false;
  return deadline < now;
}

/** Sort manifests newest-first (by semver-string lex comparison). */
export function sortByNewest(manifests: readonly OtaManifest[]): OtaManifest[] {
  return [...manifests].sort((a, b) => (b.version > a.version ? 1 : b.version < a.version ? -1 : 0));
}
