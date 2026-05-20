/* eslint-env node */
module.exports = {
  root: true,
  parser: "@typescript-eslint/parser",
  parserOptions: {
    project: ["./tsconfig.json", "./tsconfig.test.json"],
    tsconfigRootDir: __dirname,
    sourceType: "module",
  },
  plugins: ["@typescript-eslint"],
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/strict-type-checked",
    "plugin:@typescript-eslint/stylistic-type-checked",
  ],
  rules: {
    "@typescript-eslint/no-floating-promises": "error",
    "@typescript-eslint/no-misused-promises": "error",
    "@typescript-eslint/consistent-type-imports": "error",
    "@typescript-eslint/no-unused-vars": [
      "error",
      { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
    ],
    // The public API forbids `any` (SC-004 binding gate); the contract
    // test in tests/contract/no-any-in-public.test.ts enforces that on
    // the emitted .d.ts. Internally we lean on `unknown`.
    "@typescript-eslint/no-explicit-any": "error",
  },
  ignorePatterns: ["dist/**", "node_modules/**", "coverage/**", "*.config.ts", "*.config.cjs"],
  overrides: [
    {
      // Tests get a slightly looser regime — `expect(x).toBeDefined()` reasonably uses any.
      files: ["tests/**/*.ts"],
      rules: {
        "@typescript-eslint/no-explicit-any": "warn",
        "@typescript-eslint/no-non-null-assertion": "off",
      },
    },
  ],
};
