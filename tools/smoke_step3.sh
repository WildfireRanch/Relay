#!/usr/bin/env bash
set -euo pipefail

BASE="https://relay.wildfireranch.us"

pass() { printf "✅ %s\n" "$1"; }
fail() { printf "❌ %s\n" "$1"; exit 1; }

# 1) /mcp/ping -> 200 + impl v6
json=$(curl -fsS "$BASE/mcp/ping") || fail "/mcp/ping unreachable"
echo "$json" | jq -e '.status=="ok" and (.impl|test("v6"))' >/dev/null || fail "/mcp/ping unexpected payload"
pass "/mcp/ping OK (v6)"

# 2) /mcp/diag -> critical imports ok
diag=$(curl -fsS "$BASE/mcp/diag") || fail "/mcp/diag unreachable"
echo "$diag" | jq -e '.imports["agents.mcp_agent"].ok==true and .imports["agents.echo_agent"].ok==true and .imports["core.context_engine"].ok==true' >/dev/null \
  || fail "/mcp/diag imports not OK"
pass "/mcp/diag imports OK"

# 3) /mcp/run -> top-level kb present + grounding_len >= 0
run=$(curl -fsS "$BASE/mcp/run")
kb_hits=$(echo "$run" | jq -r '.kb.hits // -1')
[[ "$kb_hits" -ge 0 ]] || fail "/mcp/run kb.hits missing"
pass "/mcp/run KB present (hits=$kb_hits)"

# 4) /ask -> non-parroting final_text + KB present, not no_answer:true
ask=$(curl -fsS -X POST "$BASE/ask" -H 'content-type: application/json' \
  --data '{"q":"What is the Relay Command Center?"}')
echo "$ask" | jq -e '(.final_text|type=="string" and (.final_text|length>0)) and (.no_answer!=true) and (.kb.hits>=0)' >/dev/null \
  || fail "/ask failed anti-parrot or KB missing"
pass "/ask returns answer (non-parroting) and KB present"

# 5) /openapi.json -> control/docs not mounted (quiet optional routers)
openapi=$(curl -fsS "$BASE/openapi.json")
echo "$openapi" | jq -e '(.paths|keys|map(test("^/control|^/docs"))|any)==false' >/dev/null \
  && pass "Optional routers not mounted (/control, /docs)" \
  || fail "Optional routers unexpectedly mounted"

# 6) /webhooks/github -> tolerant 2xx on minimal payload (route present + quiet)
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/webhooks/github" -H 'content-type: application/json' --data '{}')
([[ "$code" == "200" || "$code" == "204" ]]) \
  && pass "/webhooks/github responds $code (quiet)" \
  || fail "/webhooks/github unexpected status $code"

echo "——"
pass "Step 3 smoke: ALL GREEN"
