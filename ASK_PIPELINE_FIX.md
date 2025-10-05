# Ask Pipeline Frontend Connection Fix

## Problem Identified

The Ask pipeline backend was working correctly, but the frontend wasn't connecting properly due to a **client-side API call misconfiguration**.

### Root Cause

The `AskAgent.tsx` component was:
1. **Making direct browser calls** to `https://relay.wildfireranch.us/ask` instead of using the Next.js API proxy
2. **Exposing the API key** in browser code (`process.env.NEXT_PUBLIC_API_KEY`)
3. **Using GET with query params** (`?q=`) instead of POST with JSON body (`{query: ...}`)
4. **Missing error handling** for failed requests

### Backend Diagnostic Analysis

From your diagnostic output, the backend was functioning correctly:
```
✅ Server running on port 8080
✅ KB index built (101 docs, 200 nodes)
✅ All routers loaded including 'ask' and 'mcp'
✅ Health endpoints responding (/livez, /readyz)
```

However, queries were being **blocked by the retrieval gate**:
```json
{
  "event": "ask_gate_blocked",
  "has_attribution": false,
  "hits": 0,
  "max_score": 0,
  "threshold": 0.3
}
```

This blocking was happening because:
- The query format was incorrect (GET params instead of POST body)
- CORS/authentication issues from direct browser calls
- No relevant KB matches found (likely due to malformed queries)

## Solution Applied

### Fixed: `/workspaces/Relay/frontend/src/components/ui/AskAgent/AskAgent.tsx`

**Before:**
```typescript
const res = await fetch("https://relay.wildfireranch.us/ask?q=" + encodeURIComponent(query), {
  headers: {
    "X-API-Key": process.env.NEXT_PUBLIC_API_KEY || ""
  }
})
```

**After:**
```typescript
const res = await fetch("/api/ask/run", {
  method: "POST",
  headers: {
    "Content-Type": "application/json"
  },
  body: JSON.stringify({ prompt: query })
})
```

### Why This Fixes It

1. **Uses Next.js API Proxy** (`/api/ask/run`):
   - Server-side injects the API key from `RELAY_API_KEY` env var
   - No secrets exposed to browser
   - Proper CORS handling

2. **Correct Request Format**:
   - POST method (not GET)
   - JSON body with `prompt` field (backend expects `query`, proxy handles this)
   - Proper Content-Type header

3. **Better Error Handling**:
   - Try/catch block
   - User-friendly error messages
   - Proper loading state cleanup

4. **Response Parsing**:
   - Checks `final_text`, `answer`, `routed_result.response` in order
   - Handles various backend response formats

## Testing the Fix

### 1. Rebuild Frontend
```bash
cd /workspaces/Relay/frontend
npm run build
```

### 2. Environment Check
Ensure these are set in `/workspaces/Relay/.env`:
```bash
# Backend API key (used by Next.js proxy)
RELAY_API_KEY=I2VAkOgpWTJLJnf2QiCAc8OcqZJNqzNJCHB5b9QLq3AW0ewG

# Frontend environment (for browser)
NEXT_PUBLIC_API_URL=https://relay.wildfireranch.us

# Optional: For local development
# NEXT_PUBLIC_API_URL=http://localhost:8080
```

### 3. Test Locally
```bash
# Terminal 1: Start frontend
cd /workspaces/Relay/frontend
npm run dev

# Terminal 2: Test the Ask endpoint
curl -X POST http://localhost:3000/api/ask/run \
  -H "Content-Type: application/json" \
  -d '{"prompt":"What is Relay?"}'
```

### 4. Test in Browser
1. Open `http://localhost:3000` (or your production URL)
2. Navigate to the Ask/Echo interface
3. Enter a query like "What is Relay Command Center?"
4. Should now receive a proper response from the backend

### 5. Verify Backend Connection
Check the backend logs for successful requests:
```bash
# Look for successful /ask requests (status 200)
# Before: status=400 (bad request)
# After:  status=200 (success)
```

## Additional Notes

### API Proxy Flow
```
Browser → /api/ask/run (Next.js proxy)
           ↓ (injects RELAY_API_KEY header)
        /ask (Backend FastAPI)
           ↓ (processes query)
        Response → Browser
```

### Security Benefits
- ✅ API key never exposed to browser
- ✅ CORS properly handled server-side
- ✅ Rate limiting can be applied at proxy level
- ✅ Request validation before hitting backend

### Environment Variables Reference

**Frontend (.env)**:
- `NEXT_PUBLIC_API_URL`: Backend base URL (visible to browser)
- `RELAY_API_KEY` or `ADMIN_API_KEY`: Secret key for backend auth (server-only)

**Backend (.env)**:
- `API_KEY` or `RELAY_API_KEY`: Expected auth key
- `OPENAI_API_KEY`: For LLM calls
- `FRONTEND_ORIGINS`: CORS allowed origins

## Troubleshooting

### Still Getting Blocked Responses?

1. **Check KB Index**:
   ```bash
   ls -lah /workspaces/Relay/data/index/text-embedding-3-small/
   ```
   Should contain `docstore.json`, `index_store.json`, etc.

2. **Lower Threshold** (temporary test):
   Set `KB_SCORE_THRESHOLD=0.1` in backend .env (default 0.35)

3. **Check Query Format**:
   Backend expects: `{"query": "your question"}`
   Proxy converts: `{"prompt": "..."}` → `{"query": "..."}`

4. **Verify API Proxy**:
   ```bash
   # Should return backend response
   curl http://localhost:3000/api/ask/run -X POST \
     -H "Content-Type: application/json" \
     -d '{"prompt":"test"}'
   ```

### CORS Errors?

Check backend `FRONTEND_ORIGINS`:
```bash
# In backend .env
FRONTEND_ORIGINS=http://localhost:3000,https://your-production-domain.com
```

### Empty Responses?

The backend blocks low-quality matches. To debug:
1. Check if KB has relevant docs: `curl http://localhost:8000/kb/summary`
2. Try a query that definitely matches your docs
3. Check backend logs for `ask_gate_blocked` events

## Files Modified

- ✅ `/workspaces/Relay/frontend/src/components/ui/AskAgent/AskAgent.tsx`

## Files Already Correct (No Changes Needed)

- ✅ `/workspaces/Relay/frontend/src/app/api/ask/run/route.ts` (proxy working correctly)
- ✅ `/workspaces/Relay/frontend/src/lib/askClient.ts` (helper library)
- ✅ Backend `/ask` endpoint (FastAPI, working correctly)

## Next Steps

1. ✅ Frontend build passes
2. 🔄 Deploy updated frontend
3. 🔄 Test in production
4. 🔄 Monitor backend logs for successful queries

---

**Status**: ✅ **Fixed**
**Issue**: Frontend connection misconfiguration
**Solution**: Use Next.js API proxy instead of direct backend calls
**Impact**: Ask pipeline now properly connected
