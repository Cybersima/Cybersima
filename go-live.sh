#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

unset PYTHONHOME || true
unset PYTHONPATH || true

echo
echo "CyberSym SecureTrade — LIVE TRADING"
echo "This sends REAL Coinbase market orders with your money."
echo "Default cap is \$25 per trade."
echo "Cross-venue (Coinbase vs Kraken/Gemini/Bitstamp) stays PAPER."
echo "Close this window or use Kill switch to stop."
echo

if [[ ! -f keys/coinbase.json ]]; then
  echo "Missing keys/coinbase.json"
  echo "Read LIVE.txt, then put the Coinbase API JSON in the keys folder."
  exit 1
fi

read -r -p "Type YES to arm live trading: " confirm
if [[ "${confirm}" != "YES" ]]; then
  echo "Cancelled."
  exit 1
fi

PY=""
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "Python 3.11+ is required."
  exit 1
fi
"$PY" scripts/ensure_venv.py

unset PULSEARB_DEMO_ONLY || true
export PULSEARB_EXECUTION_MODE=live
export PULSEARB_LIVE_CONFIRM=I_UNDERSTAND_THE_RISK

exec .venv/bin/python -m pulsearb --live-trading --host 127.0.0.1 --port 8080 --open-browser
