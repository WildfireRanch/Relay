#!/usr/bin/env bash
set -euo pipefail

# --- settings ---------------------------------------------------------------
BUNDLE_NAME="${BUNDLE_NAME:-relay-ask-audit}"
OUT_ZIP="./${BUNDLE_NAME}.zip"
OUT_TGZ="./${BUNDLE_NAME}.tar.gz"

# Files in scope for the /ask pipeline audit
FILES=(
  "routes/ask.py"
  "agents/mcp_agent.py"
  "agents/planner_agent.py"
  "agents/echo_agent.py"
  "services/context_injector.py"
  "services/semantic_retriever.py"
  "services/kb.py"
  "utils/openai_client.py"
  "core/logging.py"
  ".github/workflows"
)

# Optional helpful extras if present
EXTRAS=(
  "tests"
  "pyproject.toml"
  "requirements.txt"
  "requirements-dev.txt"
  ".env.example"
  "README.md"
)

# --- helpers ---------------------------------------------------------------
have_cmd() { command -v "$1" >/dev/null 2>&1; }

add_if_exists() {
  local p="$1"
  if [ -e "$p" ]; then
    echo "$p"
  fi
}

# --- main ------------------------------------------------------------------
# Ensure we are at repo root (contains .git)
if [ ! -d ".git" ]; then
  echo "✗ Please run from the repository root (where .git lives)." >&2
  exit 1
fi

# Build the final list (only existing files/dirs)
INCLUDE=()
for f in "${FILES[@]}"; do INCLUDE+=("$(add_if_exists "$f")"); done
for f in "${EXTRAS[@]}"; do
  ex="$(add_if_exists "$f" || true)"
  [ -n "${ex:-}" ] && INCLUDE+=("$ex")
done

# Remove empties
TMP=()
for i in "${INCLUDE[@]}"; do [ -n "$i" ] && TMP+=("$i"); done
INCLUDE=("${TMP[@]}")

if [ ${#INCLUDE[@]} -eq 0 ]; then
  echo "✗ No target files found. Are paths correct?" >&2
  exit 1
fi

echo "→ Files and folders to include:"
for i in "${INCLUDE[@]}"; do echo "  - $i"; done

# Install zip if missing (Codespaces usually has it, but just in case)
if ! have_cmd zip; then
  echo "ℹ zip not found; installing..."
  sudo apt-get update -y >/dev/null
  sudo apt-get install -y zip >/dev/null
fi

# Create zip (prefer zip for easy upload here)
echo "→ Creating $OUT_ZIP"
rm -f "$OUT_ZIP" "$OUT_TGZ"
zip -r "$OUT_ZIP" "${INCLUDE[@]}" \
  -x "**/__pycache__/*" "**/.pytest_cache/*" "**/.mypy_cache/*" \
     "**/.DS_Store" "**/node_modules/*" "**/.venv/*" >/dev/null

if [ ! -f "$OUT_ZIP" ]; then
  echo "⚠ zip failed, falling back to tar.gz"
  tar --exclude='**/__pycache__' \
      --exclude='**/.pytest_cache' \
      --exclude='**/.mypy_cache' \
      --exclude='**/.DS_Store' \
      --exclude='**/node_modules' \
      --exclude='**/.venv' \
      -czf "$OUT_TGZ" "${INCLUDE[@]}"
fi

# Optional: publish as a secret Gist if --gist is passed and gh is available
if [ "${1:-}" = "--gist" ]; then
  if have_cmd gh; then
    BUNDLE_PATH="$OUT_ZIP"
    [ -f "$OUT_TGZ" ] && BUNDLE_PATH="$OUT_TGZ"
    echo "→ Publishing secret Gist via GitHub CLI…"
    # gh will print the Gist URL on success
    gh gist create "$BUNDLE_PATH" --public=false -d "Relay /ask audit bundle ($(date -u +%F))"
  else
    echo "⚠ gh CLI not found; skipping Gist publish." >&2
  fi
fi

echo "✅ Done."
echo "   Bundle at: $( [ -f "$OUT_ZIP" ] && echo "$OUT_ZIP" || echo "$OUT_TGZ" )"
