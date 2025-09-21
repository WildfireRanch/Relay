#!/usr/bin/env bash
set -euo pipefail
: "${RELAY_URL:?RELAY_URL not set}"
: "${RELAY_API_KEY:?RELAY_API_KEY not set}"

DATE_DIR="ops/audits/$(date -u +%F)"
mkdir -p "$DATE_DIR"

curl -sS "$RELAY_URL/__router_map?verbose=1"                > "$DATE_DIR/router_map.json"
curl -sS "$RELAY_URL/readyz"                                > "$DATE_DIR/readyz.json"
curl -sS "$RELAY_URL/livez"                                 > "$DATE_DIR/livez.json"
curl -sS -H "X-API-Key: $RELAY_API_KEY" \
     "$RELAY_URL/kb/search?query=tarana&k=3"                > "$DATE_DIR/kb_search_probe.json"

echo "Wrote: $DATE_DIR/{router_map.json,readyz.json,livez.json,kb_search_probe.json}"
