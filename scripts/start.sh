#!/usr/bin/env bash
# Start Lockwell locally in one command (API + built UI on one port).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${PORT:-5000}"
# Bind on all interfaces so a Kali/gateway agent on the LAN can reach the API.
HOST="${HOST:-0.0.0.0}"

echo "==> Lockwell local package"
echo "    root: $ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required." >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "Node.js/npm is required to build the UI." >&2
  exit 1
fi

echo "==> Building frontend"
(
  cd frontend
  if [[ ! -d node_modules ]]; then
    npm install
  fi
  npm run build
)

echo "==> Preparing Python environment"
(
  cd backend
  if [[ ! -d .venv ]]; then
    python3 -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -q -r requirements.txt
)

echo "==> Starting Lockwell on http://${HOST}:${PORT}"
echo "    Open that URL in your browser."
echo "    Optional Network Guard demo (second terminal):"
echo "      ./scripts/start-network-guard.sh"
echo

cd backend
# shellcheck disable=SC1091
source .venv/bin/activate
export HOST PORT
export FLASK_DEBUG="${FLASK_DEBUG:-0}"
export SECRET_KEY="${SECRET_KEY:-lockwell-local-dev-key}"
export MONITOR_PEPPER="${MONITOR_PEPPER:-lockwell-local-pepper}"
exec python app.py
