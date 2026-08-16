#!/usr/bin/env bash
# Run Network Guard in Linux gateway enforce mode (nftables + live capture).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

API="${LOCKWELL_API:-}"
TOKEN="${LOCKWELL_GUARD_TOKEN:-}"
IFACE="${LOCKWELL_IFACE:-eth0}"

if [[ -z "$TOKEN" ]]; then
  echo "Set LOCKWELL_GUARD_TOKEN first (from the Network Guard page)." >&2
  exit 2
fi
if [[ -z "$API" ]]; then
  echo "Set LOCKWELL_API to your dashboard host, e.g. http://192.168.1.50:5000" >&2
  exit 2
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -r requirements.txt
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "Starting gateway enforce on iface=$IFACE api=$API"
echo "Expected success line includes: backend=nftables live_capture=True"
exec sudo -E env LOCKWELL_API="$API" LOCKWELL_GUARD_TOKEN="$TOKEN" \
  "$(command -v python)" -m network_guard.agent --mode enforce --interface "$IFACE"
