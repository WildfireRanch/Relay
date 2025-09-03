#!/usr/bin/env bash
# forensics_askecho.sh
# Collects all relevant files + signals to debug Ask/Echo end-to-end.
# Usage: bash forensics_askecho.sh
set -euo pipefail

# -------- config --------
REPO_ROOT="${REPO_ROOT:-$(pwd)}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUTDIR="${OUTDIR:-forensics_askecho_${TS}}"
mkdir -p "${OUTDIR}"/{routes,agents,services,frontend,reports}

# ripgrep is faster/nicer; fallback to grep -R if missing
RG="$(command -v rg || true)"
GREP="${RG:-grep}"

# -------- helpers --------
copy_if_exists() {
  local src="$1"
  local dst_dir="$2"
  if [ -e "${src}" ]; then
    mkdir -p "${dst_dir}"
    cp -a "${src}" "${dst_dir}/"
  fi
}

append_if_exists() {
  local src="$1"
  local dst_file="$2"
  if [ -e "${src}" ]; then
    echo "----- ${src}" >> "${dst_file}"
    cat "${src}" >> "${dst_file}"
    echo -e "\n" >> "${dst_file}"
  fi
}

# -------- git snapshot --------
{
  echo "repo: $(basename "${REPO_ROOT}")"
  git -C "${REPO_ROOT}" rev-parse --show-toplevel || true
  git -C "${REPO_ROOT}" rev-parse HEAD || true
  git -C "${REPO_ROOT}" status -sb || true
} > "${OUTDIR}/reports/git_snapshot.txt" 2>&1 || true

# -------- canonical targets --------
# Routes most relevant
copy_if_exists routes/ask.py                "${OUTDIR}/routes"
copy_if_exists routes/mcp.py                "${OUTDIR}/routes"
copy_if_exists routes/docs.py               "${OUTDIR}/routes"
copy_if_exists routes/codex.py              "${OUTDIR}/routes"
copy_if_exists routes/control.py            "${OUTDIR}/routes"
copy_if_exists routes/search.py             "${OUTDIR}/routes"
copy_if_exists routes/kb.py                 "${OUTDIR}/routes"
copy_if_exists routes/status.py             "${OUTDIR}/routes"
copy_if_exists routes/debug.py              "${OUTDIR}/routes"
copy_if_exists routes/admin.py              "${OUTDIR}/routes"

# Agents (planner/echo/MCP + likely collaborators)
copy_if_exists agents/planner_agent.py      "${OUTDIR}/agents"
copy_if_exists agents/echo_agent.py         "${OUTDIR}/agents"
copy_if_exists agents/mcp_agent.py          "${OUTDIR}/agents"
copy_if_exists agents/docs_agent.py         "${OUTDIR}/agents"
copy_if_exists agents/codex_agent.py        "${OUTDIR}/agents"
copy_if_exists agents/control_agent.py      "${OUTDIR}/agents"
copy_if_exists agents/memory_agent.py       "${OUTDIR}/agents"
copy_if_exists agents/janitor_agent.py      "${OUTDIR}/agents"
copy_if_exists agents/simulation_agent.py   "${OUTDIR}/agents"
copy_if_exists agents/metaplanner_agent.py  "${OUTDIR}/agents"

# Services (context, KB, openai client, finalizer)
copy_if_exists services/context_injector.py "${OUTDIR}/services"
copy_if_exists services/kb.py               "${OUTDIR}/services"
copy_if_exists services/openai_client.py    "${OUTDIR}/services"
copy_if_exists services/answer_finalizer.py "${OUTDIR}/services" # if you added it
copy_if_exists services/cache.py            "${OUTDIR}/services" # optional

# Frontend pieces (answer rendering + meta)
copy_if_exists frontend/src/lib/pickFinalText.ts         "${OUTDIR}/frontend"
copy_if_exists frontend/src/lib/toMDString.ts            "${OUTDIR}/frontend"
copy_if_exists frontend/src/components/SafeMarkdown.tsx  "${OUTDIR}/frontend"
copy_if_exists frontend/src/components/common/MetaBadges.tsx "${OUTDIR}/frontend"
# Core renderers that must use pickFinalText + MetaBadges
copy_if_exists frontend/src/components/AskAgent/ChatMessage.tsx "${OUTDIR}/frontend"
copy_if_exists frontend/src/components/DocsViewer.tsx           "${OUTDIR}/frontend"
copy_if_exists frontend/src/components/DocsViewer/AgentDebugTab.tsx "${OUTDIR}/frontend"

# Also grab server main/router map
copy_if_exists main.py "${OUTDIR}"

# -------- repository-wide signal scans --------
REPORT="${OUTDIR}/reports/signals.txt"
touch "${REPORT}"

echo "### Endpoints (.post/.get) in routes" >> "${REPORT}"
${GREP} -n --pretty --glob '!**/node_modules/**' -e '@router\.post' -e '@router\.get' routes 2>/dev/null || true >> "${REPORT}"

echo -e "\n### Where final_text is set (ensure finalizer present)" >> "${REPORT}"
${GREP} -n --pretty -e 'final_text' routes 2>/dev/null || true >> "${REPORT}"

echo -e "\n### /mcp/run handler presence" >> "${REPORT}"
${GREP} -n --pretty -e '"/mcp/run"' -e '@router\.post\("/mcp/run' routes 2>/dev/null || true >> "${REPORT}"

echo -e "\n### Normalizer in MCP (answer extraction)" >> "${REPORT}"
${GREP} -n --pretty agents/mcp_agent.py -e '_normalize_routed_result' -e '_best_string' 2>/dev/null || true >> "${REPORT}"

echo -e "\n### Echo returns text (MCP-friendly)" >> "${REPORT}"
${GREP} -n --pretty agents/echo_agent.py -e '"text"' -e 'answer' 2>/dev/null || true >> "${REPORT}"

echo -e "\n### Docs/Codex/Control return human-friendly text" >> "${REPORT}"
${GREP} -n --pretty agents/docs_agent.py -e '"text"' -e 'summary' -e 'answer' 2>/dev/null || true >> "${REPORT}"
${GREP} -n --pretty agents/codex_agent.py -e '"text"' -e 'summary' -e 'message' 2>/dev/null || true >> "${REPORT}"
${GREP} -n --pretty agents/control_agent.py -e '"text"' -e 'action' 2>/dev/null || true >> "${REPORT}"

echo -e "\n### Frontend uses shared pickFinalText (no duplicates)" >> "${REPORT}"
${GREP} -n --pretty frontend -e 'pickFinalText' 2>/dev/null || true >> "${REPORT}"
${GREP} -n --pretty frontend -e 'function pickFinalText' 2>/dev/null || true >> "${REPORT}"

echo -e "\n### MetaBadges usage: old 'meta=' vs new 'items='" >> "${REPORT}"
${GREP} -n --pretty frontend -e '<MetaBadges meta=' -e '<MetaBadges items=' 2>/dev/null || true >> "${REPORT}"

echo -e "\n### Defaults forcing role='docs' (bypass planner)" >> "${REPORT}"
${GREP} -n --pretty -e 'role[[:space:]]*[:=][[:space:]]*["'\'']docs["'\'']' frontend routes agents 2>/dev/null || true >> "${REPORT}"

echo -e "\n### Planner FA + anti-parrot gates present" >> "${REPORT}"
${GREP} -n --pretty agents/planner_agent.py -e '_looks_like_definition' -e '_key_from_query' -e '_extract_definition_from_context' 2>/dev/null || true >> "${REPORT}"

echo -e "\n### /ask controller finalizer present?" >> "${REPORT}"
${GREP} -n --pretty routes/ask.py -e 'final_text' -e 'reply_head' -e 'routed_result' 2>/dev/null || true >> "${REPORT}"

# -------- manifests --------
# List everything copied
( cd "${OUTDIR}" && find . -type f | sort ) > "${OUTDIR}/reports/manifest.txt"

# Quick LOC per file
{
  echo "Lines of code by file:"
  while IFS= read -r f; do
    wc -l "${f}"
  done < <(find "${OUTDIR}" -type f ! -path "*/reports/*" | sort)
} > "${OUTDIR}/reports/loc.txt"

# -------- tarball --------
tar -czf "${OUTDIR}.tar.gz" "${OUTDIR}" >/dev/null 2>&1 || true

echo "Forensics bundle ready: ${OUTDIR}/"
echo "Tarball: ${OUTDIR}.tar.gz"
echo "Key report: ${OUTDIR}/reports/signals.txt"
