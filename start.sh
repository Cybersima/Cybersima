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

echo "Starting CyberSym SecureTrade 2 command center on http://127.0.0.1:8000"
echo "Paper trading is the default. The engine keeps running in this window."
exec .venv/bin/python -m securetrade desktop --demo --host 127.0.0.1 --port 8000
