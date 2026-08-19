#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PY=""
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "Python 3.11+ is required. Install it from https://www.python.org/downloads/"
  exit 1
fi

if [[ ! -d .venv ]]; then
  echo "Creating virtual environment..."
  "$PY" -m venv .venv
  .venv/bin/python -m pip install -U pip
  .venv/bin/pip install -e .
fi

MODE="--demo"
if [[ "${1:-}" == "--live" ]]; then
  MODE=""
  echo "Starting CyberSym SecureTrade with live Coinbase / Kraken / Gemini / Bitstamp / Yahoo data (paper trading)."
else
  echo "Starting CyberSym SecureTrade demo on http://127.0.0.1:8080"
fi

URL="http://127.0.0.1:8080"
if command -v open >/dev/null 2>&1; then
  (sleep 2 && open "$URL") &
elif command -v xdg-open >/dev/null 2>&1; then
  (sleep 2 && xdg-open "$URL") &
fi

echo "Leave this window open. Close it or press Ctrl+C to stop."
# shellcheck disable=SC2086
exec .venv/bin/python -m pulsearb $MODE --host 127.0.0.1 --port 8080
