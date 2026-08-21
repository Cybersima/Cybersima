#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

unset PYTHONHOME || true
unset PYTHONPATH || true

echo
echo "CyberSym SecureTrade — LIVE TRADING"
echo "This sends REAL market orders with your money (Coinbase or Kraken)."
echo "Each tap is \$1-\$25 (default \$5). Session budget \$25."
echo "Live Auto only runs inside the time window you set on the dashboard."
echo "Cross-venue (Coinbase vs Kraken) stays PAPER."
echo "Close this window or use Kill switch to stop."
echo

if [[ ! -f keys/coinbase.json && ! -f keys/kraken.json ]]; then
  echo "Missing keys/coinbase.json and keys/kraken.json"
  echo "Read LIVE.txt. Save the key file for the exchange you will use."
  echo "Then run ./check-live.sh before this file."
  exit 1
fi

if [[ ! -d .venv ]]; then
  echo "Run ./install.sh first."
  exit 1
fi

echo "Running live ready check..."
echo
.venv/bin/python -m pulsearb --check-live

read -r -p "Type YES to arm live trading: " confirm
if [[ "${confirm}" != "YES" ]]; then
  echo "Cancelled."
  exit 1
fi

unset PULSEARB_DEMO_ONLY || true
export PULSEARB_EXECUTION_MODE=live
export PULSEARB_LIVE_CONFIRM=I_UNDERSTAND_THE_RISK

exec .venv/bin/python -m pulsearb --live-trading --host 127.0.0.1 --port 8080 --open-browser
