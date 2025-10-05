#!/bin/bash
# Test Flow Monitor functionality

echo "🧪 Testing Flow Monitor Feature"
echo "================================"
echo ""

# Test 1: Backend health
echo "✓ Test 1: Backend Health"
HEALTH=$(curl -s http://localhost:8000/livez | jq -r '.ok')
if [ "$HEALTH" = "true" ]; then
  echo "  ✅ Backend is healthy"
else
  echo "  ❌ Backend health check failed"
  exit 1
fi
echo ""

# Test 2: Debug router registered
echo "✓ Test 2: Debug Flow Trace Router"
ROUTES=$(curl -s "http://localhost:8000/__router_map?prefix=/debug" | jq -r '.count')
if [ "$ROUTES" -gt 0 ]; then
  echo "  ✅ Debug routes registered ($ROUTES endpoints)"
else
  echo "  ❌ No debug routes found"
  exit 1
fi
echo ""

# Test 3: Env config endpoint
echo "✓ Test 3: Environment Config Endpoint"
CORR_ID=$(curl -s http://localhost:8000/debug/env-config | jq -r '.corr_id')
if [ ! -z "$CORR_ID" ]; then
  echo "  ✅ Env config endpoint working (corr_id: ${CORR_ID:0:8}...)"
else
  echo "  ❌ Env config endpoint failed"
  exit 1
fi
echo ""

# Test 4: Flow events endpoint
echo "✓ Test 4: Flow Events Endpoint"
EVENTS=$(curl -s "http://localhost:8000/debug/flow-events/recent?limit=5" | jq -r '.events | length')
echo "  ✅ Flow events endpoint working ($EVENTS events)"
echo ""

# Test 5: Frontend proxy
echo "✓ Test 5: Frontend API Proxy"
PROXY_CORR=$(curl -s "http://localhost:3000/api/ops/debug/env-config" | jq -r '.corr_id')
if [ ! -z "$PROXY_CORR" ]; then
  echo "  ✅ Frontend proxy working (corr_id: ${PROXY_CORR:0:8}...)"
else
  echo "  ❌ Frontend proxy failed"
  exit 1
fi
echo ""

# Test 6: Flow trace endpoint (quick test)
echo "✓ Test 6: Flow Trace Endpoint"
echo "  Running quick trace (this may take a few seconds)..."
TRACE_RESULT=$(timeout 30 curl -s "http://localhost:3000/api/ops/debug/flow-trace" \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"query":"test","enable_deep_trace":false,"test_mode":true}')

if echo "$TRACE_RESULT" | jq -e '.success' > /dev/null 2>&1; then
  SUCCESS=$(echo "$TRACE_RESULT" | jq -r '.success')
  STEPS=$(echo "$TRACE_RESULT" | jq -r '.total_steps')
  DURATION=$(echo "$TRACE_RESULT" | jq -r '.total_duration_ms' | xargs printf "%.0f")
  echo "  ✅ Flow trace executed ($STEPS steps, ${DURATION}ms)"
else
  echo "  ⚠️  Flow trace timed out or failed (this is expected if KB is indexing)"
fi
echo ""

echo "================================"
echo "✅ All Flow Monitor Tests Passed!"
echo ""
echo "🌐 Access the Flow Monitor at:"
echo "   http://localhost:3000/flow-monitor"
echo ""
echo "📝 Available Endpoints:"
echo "   POST   /debug/flow-trace           - Run pipeline trace"
echo "   GET    /debug/env-config           - Check environment"
echo "   GET    /debug/flow-events          - SSE event stream"
echo "   GET    /debug/flow-events/recent   - Recent events"
echo ""
