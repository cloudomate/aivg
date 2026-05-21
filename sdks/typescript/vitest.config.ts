import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Default env is Node; contract tests opt in to happy-dom via the
    // // @vitest-environment happy-dom file directive.
    environment: "node",
    globals: false,
    setupFiles: ["./tests/helpers/setup.ts"],
    include: [
      "tests/unit/**/*.test.ts",
      "tests/contract/**/*.test.ts",
      // Integration suites are skipped unless GATEWAY_URL is set —
      // they self-`test.skip()` rather than being gated here.
      "tests/integration/**/*.spec.ts",
    ],
    exclude: ["dist/**", "node_modules/**", "tests/fixtures/**"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.ts"],
      exclude: ["src/**/*.d.ts", "src/proto/version.ts"],
      reporter: ["text", "lcov"],
      thresholds: {
        // Phase 7 polish bumps these to the documented ≥ 85% gate.
        // During MVP build-out we keep the gate loose so we can land
        // foundational tests before all branches are exercised.
        lines: 0,
        branches: 0,
        functions: 0,
        statements: 0,
      },
    },
  },
});
