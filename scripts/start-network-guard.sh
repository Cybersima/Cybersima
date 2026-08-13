#!/usr/bin/env bash
# Start the Network Guard edge agent against a local Lockwell instance.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

API="${LOCKWELL_API:-http://127.0.0.1:5000}"
MODE="${LOCKWELL_GUARD_MODE:-simulate}"

if [[ -z "${LOCKWELL_GUARD_TOKEN:-}" ]]; then
  echo "Set LOCKWELL_GUARD_TOKEN to the token shown in the Network Guard page." >&2
  echo "Example:" >&2
  echo "  export LOCKWELL_GUARD_TOKEN=..." >&2
  echo "  ./scripts/start-network-guard.sh" >&2
  exit 2
fi

if [[ ! -d .venv ]]; then
  echo "Run ./scripts/start.sh once first to create the backend venv." >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
export LOCKWELL_API="$API"
exec python -m network_guard.agent --mode "$MODE" --force-simulate
