# Alias Audit Report

**App root:** `/workspace/Relay/frontend`

## Summary

| Status | Unique Targets | Total Occurrences |
| --- | --- | --- |
| ok | 33 | 115 |
| missing | 0 | 0 |
| case-mismatch | 0 | 0 |

## Alias Configuration

- `tsconfig.json`: `baseUrl` = `.`, `paths['@/*']` = ['src/*']
- `next.config`: no custom `@` webpack alias defined (Next.js resolves via TypeScript paths).
- Verdict: alias configuration is consistent.

## Toolchain

- Node.js: `v22.19.0`
- npm: `11.4.2`

## Import Findings

All `@/…` imports resolved to existing files with correct casing.

## Top Offenders

None – no missing or mis-cased imports detected.

## Proposed Fixes

- No alias or import corrections required; configuration already consistent.

## Build Verification

- `CI=1 npx next build` failed with React invariant 31 while pre-rendering `/404` (see `alias_build.log`). The error is unrelated to path aliases.
