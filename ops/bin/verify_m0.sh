#!/usr/bin/env bash
set -euo pipefail
: "${RELAY_URL:?RELAY_URL not set}"
: "${RELAY_API_KEY:?RELAY_API_KEY not set}"

OUT="ops/checks/contracts.json"
TMP="$(mktemp)"
function probe() {
  local name="$1" url="$2" header_opt="$3"
  local code body ct
  if [[ -n "$header_opt" ]]; then
    code=$(curl -sS -o "$TMP" -w "%{http_code}" -H "$header_opt" "$url")
  else
    code=$(curl -sS -o "$TMP" -w "%{http_code}" "$url")
  fi
  ct=$(file -b --mime-type "$TMP" || true)
  body=$(head -c 300 "$TMP" | tr '\n' ' ' | sed 's/"/\\"/g')
  echo "{\"name\":\"$name\",\"url\":\"$url\",\"status\":$code,\"content_type\":\"$ct\",\"body_head\":\"$body\"}"
}

{
  echo "["
  probe "router_map" "$RELAY_URL/__router_map?verbose=1" ""
  echo ","
  probe "readyz"     "$RELAY_URL/readyz" ""
  echo ","
  probe "livez"      "$RELAY_URL/livez" ""
  echo ","
  probe "kb_search"  "$RELAY_URL/kb/search?query=tarana&k=3" "X-API-Key: $RELAY_API_KEY"
  echo "]"
} > "$OUT"

echo "Wrote: $OUT"
