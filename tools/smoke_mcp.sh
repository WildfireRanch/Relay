#!/usr/bin/env bash
set -euo pipefail
BASE="${1:-https://relay.wildfireranch.us}"
CID="smoke-mcp-$(date +%s)"

echo "== /mcp/diag =="
curl -sS "$BASE/mcp/diag" | jq '{imports: .imports, env: .env}'

echo "== /mcp/run =="
curl -sS "$BASE/mcp/run" \
  -H "Content-Type: application/json" \
  -H "X-Corr-Id: $CID" \
  -d '{"query":"What is the Relay Command Center?"}' \
| tee /tmp/mcp.json \
| jq '{kb: (.meta.kb // null), grounding_len: ((.routed_result.grounding // [])|length)}'
