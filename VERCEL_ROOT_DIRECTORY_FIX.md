# Vercel Root Directory Fix

## Problem

Vercel was trying to build from the monorepo root, causing path confusion with `--prefix frontend` creating `frontend/frontend/` paths.

## Solution

**Two-part fix:**

### 1. Move vercel.json ✅ (Done)
- **Commit**: `cdb6224`
- **Change**: Moved `vercel.json` from root to `frontend/` directory
- **Why**: Config is now relative to frontend

### 2. Update Vercel Project Settings ⚠️ (You need to do this)

**Go to Vercel Dashboard and update:**

1. Visit https://vercel.com/dashboard
2. Select your Relay project
3. Go to **Settings** → **General**
4. Find **Root Directory** section
5. Set to: `frontend`
6. Click **Save**

### Alternative: Set via CLI

If you prefer command line:

```bash
# Install Vercel CLI if needed
npm i -g vercel

# Link project
vercel link

# Set root directory
vercel project set-root-directory frontend
```

## Why This Is Needed

**Monorepo Structure**:
```
/workspaces/Relay/           ← Repo root (Python backend)
├── frontend/                ← Next.js app (THIS should be Vercel root)
│   ├── package.json
│   ├── vercel.json
│   ├── src/
│   └── .next/
├── agents/                  ← Python
├── routes/                  ← Python
└── main.py                  ← Python
```

**Without setting root directory:**
- Vercel runs from `/workspaces/Relay/`
- Commands like `npm install --prefix frontend` create wrong paths
- Build fails with `ENOENT` errors

**With root directory = `frontend`:**
- Vercel runs from `/workspaces/Relay/frontend/`
- All paths are correct
- Build succeeds ✅

## Verification

After setting root directory in Vercel dashboard, the next deployment should:

1. ✅ Run install from frontend directory
2. ✅ Find package.json correctly
3. ✅ Build Next.js app successfully
4. ✅ Deploy without errors

## Current Status

- ✅ vercel.json moved to frontend/
- ✅ Config simplified (uses Next.js defaults)
- ✅ Functions path fixed (src/app/api/** not frontend/src/...)
- ⏳ **NEXT**: Set root directory in Vercel dashboard

---

**After you update the Vercel settings, trigger a redeploy:**
- Option 1: Push a new commit
- Option 2: Redeploy from Vercel dashboard

**Status**: ⏳ Waiting for Vercel project settings update
**Commit**: `cdb6224`
**Date**: 2025-10-05
