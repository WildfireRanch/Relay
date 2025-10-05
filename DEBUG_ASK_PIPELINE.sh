#!/bin/bash
# Debug script for Ask pipeline issues
# Run this and share the output with Claude

echo "=========================================="
echo "RELAY ASK PIPELINE DIAGNOSTIC BUNDLE"
echo "=========================================="
echo ""

# 1. Environment Check
echo "1. ENVIRONMENT VARIABLES"
echo "------------------------"
echo "ENV: ${ENV:-not set}"
echo "NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL:-not set}"
echo "API_KEY: ${API_KEY:0:10}... (truncated)"
echo "OPENAI_API_KEY: ${OPENAI_API_KEY:0:10}... (truncated)"
echo "FRONTEND_ORIGINS: ${FRONTEND_ORIGINS:-not set}"
echo ""

# 2. Backend Health
echo "2. BACKEND HEALTH"
echo "-----------------"
echo "Testing http://localhost:8000/livez:"
curl -s http://localhost:8000/livez || echo "❌ Backend not responding"
echo ""
echo ""
echo "Testing http://localhost:8000/readyz:"
curl -s http://localhost:8000/readyz | jq . 2>/dev/null || curl -s http://localhost:8000/readyz
echo ""

# 3. Ask Endpoint Direct Test
echo "3. ASK ENDPOINT DIRECT TEST (Backend)"
echo "--------------------------------------"
echo "POST http://localhost:8000/ask with test query:"
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"test"}' | jq . 2>/dev/null || echo "❌ Ask endpoint failed"
echo ""

# 4. Frontend API Proxy Test
echo "4. FRONTEND API PROXY TEST"
echo "--------------------------"
echo "Testing http://localhost:3000/api/ask/run:"
curl -s -X POST http://localhost:3000/api/ask/run \
  -H "Content-Type: application/json" \
  -d '{"question":"test"}' 2>&1 | head -20
echo ""

# 5. Browser Console Errors (if frontend is running)
echo "5. FRONTEND LOGS"
echo "----------------"
echo "Recent Next.js logs (if available):"
if [ -f ".next/trace" ]; then
  tail -20 .next/trace 2>/dev/null || echo "No trace file"
fi
echo ""

# 6. Backend Logs
echo "6. BACKEND LOGS (Last 30 lines)"
echo "--------------------------------"
if [ -f "/tmp/backend.log" ]; then
  tail -30 /tmp/backend.log
else
  echo "No backend.log found. Check uvicorn output."
fi
echo ""

# 7. Network Connectivity
echo "7. NETWORK CONNECTIVITY"
echo "-----------------------"
echo "Backend listening on:"
lsof -i :8000 2>/dev/null | grep LISTEN || echo "❌ Backend not listening on :8000"
echo ""
echo "Frontend listening on:"
lsof -i :3000 2>/dev/null | grep LISTEN || echo "❌ Frontend not listening on :3000"
echo ""

# 8. KB Index Status
echo "8. KNOWLEDGE BASE STATUS"
echo "------------------------"
python3 << 'PYEOF'
from pathlib import Path
import os

index_root = Path(os.getenv("INDEX_ROOT", "./data/index"))
if index_root.exists():
    print(f"✅ Index directory exists: {index_root}")
    files = list(index_root.rglob("*"))
    print(f"   Files in index: {len(files)}")
else:
    print(f"❌ Index directory missing: {index_root}")
    print("   Run: python -m services.kb embed")
PYEOF
echo ""

# 9. Browser DevTools Instructions
echo "9. BROWSER DEBUGGING STEPS"
echo "--------------------------"
echo "1. Open http://localhost:3000/ask in your browser"
echo "2. Open DevTools (F12)"
echo "3. Go to Console tab"
echo "4. Try submitting a query"
echo "5. Copy any errors shown in red"
echo "6. Go to Network tab"
echo "7. Submit query again"
echo "8. Find the /api/ask/run request"
echo "9. Click it and copy:"
echo "   - Status code"
echo "   - Response tab content"
echo "   - Headers tab (Request Headers)"
echo ""

echo "=========================================="
echo "END OF DIAGNOSTIC BUNDLE"
echo "=========================================="
echo ""
echo "📋 WHAT TO SHARE WITH CLAUDE:"
echo "1. Copy this entire output"
echo "2. Also share:"
echo "   - Browser console errors (red text)"
echo "   - Network tab details for /api/ask/run"
echo "   - Any error messages you see in the UI"
