# Vercel Build Fix - Tailwind Dependencies

## Problem

Vercel build was failing with:
```
Error: Cannot find module 'tailwindcss'
```

### Root Cause

Tailwind CSS and related build tools were in `devDependencies`, but Vercel's build process with npm workspaces wasn't installing dev dependencies properly during the build phase.

## Solution

Moved Tailwind CSS build dependencies from `devDependencies` to `dependencies` in [frontend/package.json](frontend/package.json):

### Moved to `dependencies`:
- `tailwindcss`: ^3.4.17
- `autoprefixer`: ^10.4.21
- `@tailwindcss/typography`: ^0.5.16

### Why This Works

1. **Build-time requirement**: Tailwind is needed during the build process, not just development
2. **Vercel optimization**: Vercel's build process may skip dev dependencies in workspace setups
3. **Best practice**: Build tools that process CSS/assets should be in `dependencies` when they're required at build time

## Commit

```bash
git commit 4576078
fix: move Tailwind to dependencies for Vercel build
```

## Verification

After this fix, Vercel build should:
1. ✅ Install tailwindcss and autoprefixer
2. ✅ Process globals.css successfully
3. ✅ Complete the build without module errors

## Related Fixes

This completes the Ask pipeline frontend deployment. Combined with the previous fix:
1. ✅ **Frontend connection**: Uses Next.js API proxy ([ASK_PIPELINE_FIX.md](ASK_PIPELINE_FIX.md))
2. ✅ **Build dependencies**: Tailwind in correct location (this fix)

## Deployment

The fix is now in main branch. Vercel should automatically:
- Detect the new commit
- Trigger a new build
- Successfully deploy the frontend

Monitor deployment at: Vercel dashboard → Relay project

---

**Status**: ✅ **Fixed and Deployed**
**Date**: 2025-10-05
**Commit**: `4576078`
