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
  echo "For real Coinbase or Kraken orders, use ./check-live.sh then ./go-live.sh after keys/coinbase.json or keys/kraken.json is in place."
else
  echo "Starting CyberSym SecureTrade..."
fi

echo "If port 8080 is already in use, the app will pick the next free port."
echo "Leave this window open. Close it or press Ctrl+C to stop."
echo "Phone app: same Wi-Fi, open the phone address printed next, type the PIN, then Add to Home Screen. See PHONE.txt"
echo "Profit report file: $(pwd)/data/CyberSym-SecureTrade-profit-report.csv"
echo "If Export fails, open that CSV in Excel or run ./Open-Report.sh"
# shellcheck disable=SC2086
exec .venv/bin/python -E -m pulsearb $MODE --host 0.0.0.0 --port 8080 --open-browser
