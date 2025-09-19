#!/usr/bin/env bash
# Minimal bootstrap for Relay local development (Python + Node).
# Usage: ./scripts/install_deps.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"

info()  { printf '\033[1;34m[setup]\033[0m %s\n' "$*"; }
error() { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; }

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  error "Python is required but not found. Install 3.10+ and re-run." 
  exit 1
fi

if [ ! -d "${VENV_DIR}" ]; then
  info "Creating virtual environment at ${VENV_DIR}"
  "${PY}" -m venv "${VENV_DIR}"
fi

# shellcheck disable=SC1090
source "${VENV_DIR}/bin/activate"
info "Using Python $(${PY} -V)"

REQ_FILE="${ROOT_DIR}/requirements.txt"
if [ -f "${REQ_FILE}" ]; then
  info "Installing Python dependencies"
  pip install --upgrade pip
  pip install -r "${REQ_FILE}"
fi

REQ_DEV_FILE="${ROOT_DIR}/requirements-dev.txt"
if [ -f "${REQ_DEV_FILE}" ]; then
  info "Installing Python dev dependencies"
  pip install -r "${REQ_DEV_FILE}"
fi

deactivate

if command -v npm >/dev/null 2>&1; then
  cd "${ROOT_DIR}" || exit 1
  info "Installing Node dependencies"
  npm install
else
  info "npm not detected; skipping Node install"
fi

info "Dependency installation complete"
