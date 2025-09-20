// File: frontend/eslint.config.mjs

import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

export default [
  {
    files: ["**/*.{js,jsx,ts,tsx}"],
    ignores: ["node_modules", ".next", "dist"],
    languageOptions: {
      parserOptions: {
        sourceType: "module",
        ecmaVersion: "latest"
      }
    },
  },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  // Final override: ensure these rules are warnings (not errors) project-wide.
  {
    files: ["**/*.{js,jsx,ts,tsx}"],
    rules: {
      "@typescript-eslint/no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_", caughtErrorsIgnorePattern: "^_" }
      ],
      "@typescript-eslint/no-explicit-any": "warn",
    },
  },
  // ── Guardrail: Disallow dynamic({ ssr:false }) in Server Components ────────
  // Flags the foot-gun that caused SSR build errors. Only triggers when the
  // file does NOT declare a top-level "use client" directive.
  {
    files: ["src/app/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "Program:not(:has(ExpressionStatement[directive='use client'])) CallExpression[callee.name='dynamic'] ObjectExpression:has(Property[key.name='ssr'][value.value=false])",
          message:
            "Use dynamic({ ssr:false }) only inside a Client Component wrapper (\"use client\").",
        },
      ],
    },
  },
];
