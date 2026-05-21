#!/usr/bin/env node
/**
 * Package size check — fails the build if `dist/index.js` gzipped
 * exceeds the budget (50 KB per spec assumptions + plan §"Performance
 * Goals"). Run via `npm run check-size` or as part of `prepublishOnly`.
 */
import { readFileSync, existsSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const dist = join(__dirname, "..", "dist");

const BUDGET_BYTES = 50 * 1024;

function checkFile(path) {
  if (!existsSync(path)) {
    console.error(`  ✗ missing: ${path}`);
    return false;
  }
  const raw = readFileSync(path);
  const gz = gzipSync(raw).length;
  const status = gz <= BUDGET_BYTES ? "✓" : "✗";
  const margin = BUDGET_BYTES - gz;
  console.log(
    `  ${status} ${path.split("/").slice(-2).join("/")}: ` +
      `${gz.toLocaleString()} B gzipped ` +
      `(budget ${BUDGET_BYTES.toLocaleString()} B, margin ${margin.toLocaleString()} B)`,
  );
  return gz <= BUDGET_BYTES;
}

console.log("=== sdks/typescript: gzipped bundle size check ===");
const okEsm = checkFile(join(dist, "index.js"));
const okCjs = checkFile(join(dist, "index.cjs"));

if (!okEsm || !okCjs) {
  console.error(
    `\n  ⚠ at least one bundle exceeds the ${BUDGET_BYTES.toLocaleString()} B budget`,
  );
  process.exit(1);
}
console.log("\n  ✓ all bundles within budget");
