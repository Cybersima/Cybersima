#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

pick=""
for cand in python3.12 python3.13 python3.11 python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then
    if "$cand" packaging/pick_python.py >/dev/null 2>&1; then
      pick="$cand"
      break
    fi
  fi
done

if [[ -z "$pick" ]]; then
  echo "SecureTrade needs regular Python 3.11–3.13 (or official 3.14)."
  echo "The experimental free-threaded build (python3.14t) cannot create a venv."
  echo "Install from https://www.python.org/downloads/"
  exit 1
fi

if [[ -x .venv/bin/python ]] && ! .venv/bin/python -c "import encodings" >/dev/null 2>&1; then
  echo "Removing broken .venv..."
  rm -rf .venv
fi

if [[ ! -x .venv/bin/python ]]; then
  echo "Installing CyberSym SecureTrade 2 with $pick..."
  "$pick" -m venv --clear .venv
  .venv/bin/python -m pip install -U pip
  .venv/bin/python -m pip install -e .
fi

echo "Starting CyberSym SecureTrade 2 command center on http://127.0.0.1:8000"
echo "Paper trading is the default. The engine keeps running in this window."
exec .venv/bin/python -m securetrade desktop --demo --host 127.0.0.1 --port 8000
