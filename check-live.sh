#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

unset PYTHONHOME || true
unset PYTHONPATH || true

echo
echo "CyberSym SecureTrade — live ready check"
echo "This does NOT send orders."
echo "It checks keys/coinbase.json and whether Coinbase will accept the key."
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
  echo "Not ready. Read LIVE.txt, fix the FAILs, then run this again."
  echo "Do not use GO-LIVE until this check passes."
else
  echo "Ready. Next step for real orders: ./go-live.sh  (Mac: Go-Live.command)"
fi
exit "$status"
