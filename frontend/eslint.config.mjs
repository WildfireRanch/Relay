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
  ...compat.extends("next/core-web-vitals", "next/typescript")
];
