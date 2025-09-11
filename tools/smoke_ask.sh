#!/usr/bin/env bash
set -euo pipefail
BASE="${1:-https://relay.wildfireranch.us}"
CID="smoke-ask-$(date +%s)"

echo "== /ask =="
curl -sS "$BASE/ask" \
  -H "Content-Type: application/json" \
  -H "X-Corr-Id: $CID" \
  -d '{"question":"What is the Relay Command Center?"}' \
| tee /tmp/ask.json \
| jq '{final_text, no_answer: (.meta.no_answer // null),
       kb: (.meta.kb // null),
       grounding_len: ((.routed_result.grounding // [])|length)}'
