/**
 * Browser live integration test (placeholder).
 *
 * Real implementation needs Playwright + a static server hosting the
 * browser-ptt example. Setting up Playwright as a dev-dep is heavier
 * than v1 needs; deferred to the Polish phase (T070+) along with the
 * CI workflow. Until then, this file documents the intended test.
 *
 * Skip-by-default; gate on GATEWAY_URL AND PLAYWRIGHT_AVAILABLE.
 */
import { describe, it } from "vitest";

const GATEWAY = process.env.GATEWAY_URL;
const PW = process.env.PLAYWRIGHT_AVAILABLE === "1";

describe.skipIf(!GATEWAY || !PW)("live: Playwright + browser-ptt example", () => {
  it.todo("registers + voice call + transcript via the static example HTML");
});
