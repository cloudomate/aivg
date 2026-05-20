import { defineConfig } from "tsup";
import { readFileSync } from "node:fs";

const pkg = JSON.parse(readFileSync("./package.json", "utf8")) as { version: string };

export default defineConfig({
  entry: { index: "src/index.ts" },
  format: ["esm", "cjs"],
  dts: true,
  sourcemap: true,
  clean: true,
  target: "es2022",
  // platform=neutral so the same artefact loads under browser, Electron, Node
  // (per plan §R-2 + spec FR-023/FR-024 — ONE compiled artefact pair, no
  // per-runtime forks). Runtime-specific behaviour (e.g. getUserMedia
  // availability) is detected at first use, never at bundle time.
  platform: "neutral",
  treeshake: true,
  minify: false,
  splitting: false,
  define: {
    __SDK_VERSION__: JSON.stringify(pkg.version),
  },
});
