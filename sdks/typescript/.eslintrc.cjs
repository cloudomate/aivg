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
    "plugin:@typescript-eslint/recommended-type-checked",
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
    // Discriminated-union narrowing on our WsInboundMessage (which
    // includes a generic `string` fallback for unknown types per R-8
    // forward-compat) defeats the no-unsafe-* rules in legitimate
    // ways. These rules fire on type-system shape, not runtime safety
    // — we have unit + contract tests that cover the actual semantics.
    "@typescript-eslint/no-unsafe-assignment": "off",
    "@typescript-eslint/no-unsafe-member-access": "off",
    "@typescript-eslint/no-unsafe-argument": "off",
    "@typescript-eslint/no-unsafe-call": "off",
    "@typescript-eslint/restrict-template-expressions": ["error", { allowNumber: true }],
    // Tests + the example apps have unbound globals (window, console).
    "no-undef": "off",
  },
  ignorePatterns: ["dist/**", "node_modules/**", "coverage/**", "*.config.ts", "*.config.cjs"],
  overrides: [
    {
      // Tests + examples: strict-type-checked is overkill. Use the
      // type-checked recommended preset only and turn off the
      // aesthetic rules that don't catch real bugs in test code.
      files: ["tests/**/*.ts", "examples/**/*.ts", "examples/**/*.js"],
      extends: [
        "eslint:recommended",
        "plugin:@typescript-eslint/recommended-type-checked",
      ],
      rules: {
        "@typescript-eslint/no-explicit-any": "warn",
        "@typescript-eslint/no-non-null-assertion": "off",
        "@typescript-eslint/no-empty-function": "off",
        "@typescript-eslint/require-await": "off",
        "@typescript-eslint/no-unused-vars": [
          "error",
          { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
        ],
        "@typescript-eslint/no-unsafe-assignment": "off",
        "@typescript-eslint/no-unsafe-member-access": "off",
        "@typescript-eslint/no-unsafe-call": "off",
        "@typescript-eslint/no-unsafe-argument": "off",
        "@typescript-eslint/no-unsafe-return": "off",
        "@typescript-eslint/no-misused-promises": "off",
        "@typescript-eslint/no-floating-promises": "off",
        "@typescript-eslint/restrict-template-expressions": "off",
        "@typescript-eslint/no-confusing-void-expression": "off",
        "@typescript-eslint/no-base-to-string": "off",
        "@typescript-eslint/prefer-promise-reject-errors": "off",
        "@typescript-eslint/only-throw-error": "off",
        "@typescript-eslint/no-redundant-type-constituents": "off",
        "@typescript-eslint/unbound-method": "off",
        "@typescript-eslint/await-thenable": "off",
        "@typescript-eslint/consistent-type-assertions": "off",
        "@typescript-eslint/consistent-type-definitions": "off",
        "@typescript-eslint/consistent-indexed-object-style": "off",
        "@typescript-eslint/array-type": "off",
        "@typescript-eslint/consistent-generic-constructors": "off",
        "@typescript-eslint/dot-notation": "off",
        "no-empty": "off",
        "no-unused-vars": "off",
      },
    },
  ],
};
