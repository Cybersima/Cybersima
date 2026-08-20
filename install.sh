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

"$PY" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" || {
  echo "Python 3.11+ is required."
  exit 1
}

if [[ ! -d .venv ]]; then
  echo "Creating virtual environment..."
  "$PY" -m venv .venv
fi
.venv/bin/python -m pip install -U pip
.venv/bin/pip install -e .
if ! .venv/bin/python scripts/crypto_ok.py; then
  echo "Repairing cryptography..."
  .venv/bin/pip install --force-reinstall "cryptography>=46" "PyJWT[crypto]>=2.10"
  .venv/bin/python scripts/crypto_ok.py
fi
echo
echo "Installed CyberSym SecureTrade."
echo "Start with: ./start.sh   or double-click start.command"
echo "Before real Coinbase orders: ./check-live.sh then ./go-live.sh"
