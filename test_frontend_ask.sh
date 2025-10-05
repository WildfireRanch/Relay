#!/bin/bash
# Test the Ask endpoint through the production backend

BACKEND_URL="https://relay.wildfireranch.us"
API_KEY=$(grep RELAY_API_KEY /workspaces/Relay/.env | cut -d= -f2)

echo "🧪 Testing Ask Pipeline Fix"
echo "============================"
echo ""
echo "Testing: POST $BACKEND_URL/ask"
echo ""

RESPONSE=$(curl -s -X POST "$BACKEND_URL/ask" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $API_KEY" \
  -d '{"query":"test connection"}')

echo "Response received:"
echo "$RESPONSE" | jq -r '.meta.route // "unknown"' 2>/dev/null | head -1

if echo "$RESPONSE" | jq -e '.meta' > /dev/null 2>&1; then
    echo "✅ Backend /ask endpoint is working"
    echo ""
    echo "Route: $(echo "$RESPONSE" | jq -r '.meta.route')"
    echo "KB Hits: $(echo "$RESPONSE" | jq -r '.kb.hits')"
    echo "Total MS: $(echo "$RESPONSE" | jq -r '.meta.timings_ms.total_ms')"
else
    echo "❌ Backend response unexpected"
    echo "$RESPONSE"
fi

echo ""
echo "Next: Deploy frontend and test through browser"
