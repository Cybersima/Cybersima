#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

unset PYTHONHOME || true
unset PYTHONPATH || true

PY=""
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "Python 3.11+ is required. Install it from https://www.python.org/downloads/"
  exit 1
fi

"$PY" scripts/ensure_venv.py

MODE="--demo"
if [[ "${1:-}" == "--live" ]]; then
  MODE=""
  echo "Starting CyberSym SecureTrade with live Coinbase / Kraken / Gemini / Bitstamp / Yahoo data (paper trading)."
  echo "For real Coinbase orders, use ./go-live.sh after keys/coinbase.json is in place."
else
  echo "Starting CyberSym SecureTrade..."
fi

echo "If port 8080 is already in use, the app will pick the next free port."
echo "Leave this window open. Close it or press Ctrl+C to stop."
echo "Profit report file: $(pwd)/data/CyberSym-SecureTrade-profit-report.csv"
echo "If Export fails, open that CSV in Excel or run ./Open-Report.sh"
# shellcheck disable=SC2086
exec .venv/bin/python -m pulsearb $MODE --host 127.0.0.1 --port 8080 --open-browser
