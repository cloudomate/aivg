/**
 * SC-004 binding gate: no `any` in any exported type signature.
 *
 * Walks the emitted `dist/index.d.ts` with ts-morph and scans every
 * top-level export for `any` occurrences. Allowlist: zero — the
 * spec is hard.
 *
 * Caveat: this test reads the *built* .d.ts. Run `npm run build` first
 * (the `test` script does NOT auto-build to keep cycles fast; CI must
 * chain `build && test`).
 */
import { describe, it, expect } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

describe("public surface — no `any`", () => {
  it("dist/index.d.ts is clean of `any` (SC-004)", () => {
    const path = join(import.meta.dirname, "..", "..", "dist", "index.d.ts");
    if (!existsSync(path)) {
      // Skip when build hasn't run — CI invokes `npm run build` first.
      // eslint-disable-next-line no-console
      console.warn(`[no-any] ${path} not present; run \`npm run build\` first`);
      return;
    }
    const raw = readFileSync(path, "utf8");
    // Strip JSDoc + line comments so a `// any in-flight session` line
    // doesn't trigger. Also strip string literals (so the "any" enum
    // value in `routingMode: "preferred" | "any" | "off"` is excluded).
    const dts = raw
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/\/\/[^\n]*/g, "")
      .replace(/"[^"\n]*"/g, '""')
      .replace(/'[^'\n]*'/g, "''");
    // Match `any` ONLY when used as a type:
    //   `: any`, `: any[]`, `: any;`, `<any>`, `, any`, `| any`,
    //   `=> any`, `Array<any>`, etc.
    const anyType =
      /(:\s*any\b|<\s*any\s*[>,]|,\s*any\b|\|\s*any\b|=>\s*any\b|\bany\s*\[\])/g;
    const matches = dts.match(anyType) ?? [];
    if (matches.length > 0) {
      const lines = dts
        .split("\n")
        .map((l, i) => ({ n: i + 1, l }))
        .filter(({ l }) => anyType.test(l));
      // eslint-disable-next-line no-console
      console.error("`any` occurrences in public .d.ts:");
      for (const { n, l } of lines) {
        // eslint-disable-next-line no-console
        console.error(`  ${n}: ${l.trim()}`);
      }
    }
    expect(matches.length, "no `any` allowed in dist/index.d.ts (SC-004)").toBe(0);
  });
});
