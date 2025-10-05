#!/bin/bash
# Direct test of the backend /ask endpoint

BACKEND_URL="https://relay.wildfireranch.us"
API_KEY=$(grep RELAY_API_KEY .env | cut -d= -f2)

echo "Testing backend /ask endpoint directly..."
echo "Backend: $BACKEND_URL"
echo ""

curl -X POST "$BACKEND_URL/ask" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $API_KEY" \
  -d '{"query":"What is Relay?"}' \
  2>/dev/null | jq '.' 2>/dev/null || echo "Response received (not JSON or parsing failed)"

echo ""
echo "Note: If you see 'ask_gate_blocked' or no_answer=true, the backend is working"
echo "but couldn't find relevant matches in the KB. This is expected if your KB"
echo "doesn't have docs about 'What is Relay'."
