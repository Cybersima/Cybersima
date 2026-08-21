#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

unset PYTHONHOME || true
unset PYTHONPATH || true

echo
echo "CyberSym SecureTrade — live ready check"
echo "This does NOT send orders."
echo "It checks keys/coinbase.json or keys/kraken.json and whether that exchange will accept the key."
echo

if [[ ! -d .venv ]]; then
  echo "Run ./install.sh first."
  exit 1
fi

set +e
.venv/bin/python -m pulsearb --check-live
status=$?
set -e
echo
if [[ "$status" -ne 0 ]]; then
  echo "Still not ready. Read the FAIL line above and LIVE.txt."
  echo "Do not use GO-LIVE until this check passes."
else
  echo "Ready. On the dashboard, stay on Paper to practice, then switch to Live."
  echo "Or run ./go-live.sh to start already live. (Mac: Go-Live.command)"
fi
exit "$status"
