// vitest setup — runs once per test file. Keep minimal; per-test fakes
// live in tests/helpers/*.ts and are imported explicitly where needed.
//
// Intentionally empty for now; the file exists so vitest.config.ts can
// declare a `setupFiles` slot we can extend later (e.g. consoleSpy
// installations for assert-on-warning tests).
export {};
