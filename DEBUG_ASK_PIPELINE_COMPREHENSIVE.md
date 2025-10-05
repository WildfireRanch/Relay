# 🔍 Comprehensive Ask Pipeline Diagnostic Prompt

## Copy this prompt and start a NEW conversation:

---

I need you to perform a comprehensive diagnostic of the Ask pipeline in my Relay Command Center, starting from the frontend and testing all the way through to the backend.

### Current Symptom
The `/admin/ask` page is showing:
```
❌ HTTP 504 — An error occurred with your deployment
FUNCTION_INVOCATION_TIMEOUT
```

### System Architecture
- **Frontend**: Next.js on Vercel (https://relay-command-center.vercel.app or similar)
- **Backend**: FastAPI on Railway (https://relay.wildfireranch.us)
- **Frontend Ask Component**: `frontend/src/components/ui/AskAgent/AskAgent.tsx`
- **API Proxy**: `frontend/src/app/api/ask/run/route.ts`
- **Backend Endpoint**: `POST /ask` on Railway

### What I Need You To Do

**Phase 1: Frontend Inspection**
1. Read and analyze `/workspaces/Relay/frontend/src/components/ui/AskAgent/AskAgent.tsx`
2. Read and analyze `/workspaces/Relay/frontend/src/app/api/ask/run/route.ts`
3. Check what URL the frontend is calling
4. Verify the request format (headers, body, method)
5. Check for any timeout configurations

**Phase 2: API Proxy Analysis**
1. Examine the Next.js API route at `/api/ask/run`
2. Check how it's forwarding to the backend
3. Verify environment variables (`NEXT_PUBLIC_API_URL`, `RELAY_API_KEY`)
4. Look for timeout settings in Vercel config
5. Check if the proxy is waiting for the backend response correctly

**Phase 3: Backend Connectivity**
1. Test the backend directly with curl:
   ```bash
   curl -X POST https://relay.wildfireranch.us/ask \
     -H "Content-Type: application/json" \
     -H "X-Api-Key: $(grep RELAY_API_KEY .env | cut -d= -f2)" \
     -d '{"query":"test"}' \
     --max-time 30 -v
   ```
2. Check Railway logs for the request
3. Measure response time
4. Look for any backend errors or timeouts

**Phase 4: Timeout Analysis**
1. Check `frontend/vercel.json` for function timeout settings
2. Look for timeout configs in `next.config.js` or `next.config.mjs`
3. Check if the backend is responding within Vercel's timeout limit (default 10s for Hobby, 60s for Pro)
4. Identify where the timeout is occurring (frontend timeout vs backend slow response)

**Phase 5: Ask Pipeline Flow Trace**
1. Trace the complete request flow:
   - Browser → Frontend component
   - Frontend → `/api/ask/run` proxy
   - Proxy → Backend `/ask`
   - Backend processing (context build, KB search, LLM)
   - Response back through the chain
2. Identify bottlenecks at each step

**Phase 6: Root Cause Analysis**
Based on your findings, determine:
- Is the backend timing out? (> 30s response)
- Is the Vercel function timing out? (default 10s)
- Is there a network connectivity issue?
- Is the request format incorrect?
- Is authentication failing?
- Is the KB search taking too long?

**Phase 7: Proposed Solutions**
After diagnosis, provide:
1. **Immediate fix**: What needs to change right now
2. **Configuration**: Any timeout or environment variable changes
3. **Code fixes**: Specific file changes needed
4. **Optimization**: If backend is slow, what's causing it

### Files to Examine

**Frontend:**
- `frontend/src/components/ui/AskAgent/AskAgent.tsx`
- `frontend/src/app/api/ask/run/route.ts`
- `frontend/vercel.json`
- `frontend/next.config.js` or `frontend/next.config.mjs`
- `frontend/.env` or `.env.local`

**Backend:**
- `routes/ask.py` (the Ask endpoint)
- `agents/mcp_agent.py` (the orchestrator)
- `core/context_engine.py` (KB search)
- `services/semantic_retriever.py` (vector search)
- `.env` (backend config)

**Logs:**
- Railway logs: `railway logs --tail 100`
- Look for the correlation ID from the error
- Check for slow queries or timeouts

### Expected Output

Provide me with:
1. ✅ **Diagnosis**: Exact location and cause of timeout
2. 🔧 **Fixes**: Specific code/config changes needed
3. ⚡ **Optimizations**: Performance improvements if needed
4. 📊 **Benchmarks**: Expected response times at each stage
5. 🧪 **Test Plan**: How to verify the fix works

### Important Notes
- The backend WAS working when tested directly with curl
- The 504 timeout suggests the issue is likely:
  - Vercel function timeout (10s default for Hobby tier)
  - Backend taking too long (> 30s)
  - Network connectivity issue between Vercel and Railway
- Don't just fix symptoms - find the root cause

### Context
Recent changes made:
1. Frontend now uses `/api/ask/run` proxy (was direct backend calls)
2. Tailwind moved to dependencies
3. Vercel config simplified, moved to `frontend/` directory
4. Deployment succeeded but `/admin/ask` times out

Start with Phase 1 and work through systematically. Use Railway CLI and curl for testing. Be thorough.

---

## Additional Debugging Commands

```bash
# Test backend directly
curl -X POST https://relay.wildfireranch.us/ask \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: YOUR_KEY" \
  -d '{"query":"quick test"}' \
  --max-time 30 -w "\nTime: %{time_total}s\n"

# Check Railway logs with grep
railway logs --tail 200 | grep -E "(POST /ask|timeout|error|504)"

# Test the Vercel API proxy locally
cd frontend && npm run dev
# Then curl http://localhost:3000/api/ask/run

# Check Vercel function logs
# (You'll need to check the Vercel dashboard for this)
```

---

**Start your investigation and provide a comprehensive report with specific fixes.**
