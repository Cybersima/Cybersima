#!/usr/bin/env bash
# Copy the running profit report next to this script and open it.
set -euo pipefail
cd "$(dirname "$0")"
SRC="data/CyberSym-SecureTrade-profit-report.csv"
if [[ ! -f "$SRC" ]]; then
  echo "No profit report found yet."
  echo "Expected file: $(pwd)/$SRC"
  echo "Leave SecureTrade running so it can write rows, then try again."
  exit 1
fi
DEST="${HOME}/Desktop/CyberSym-SecureTrade-profit-report.csv"
mkdir -p "${HOME}/Desktop"
cp -f "$SRC" "$DEST"
echo "Copied report to: $DEST"
if command -v open >/dev/null 2>&1; then
  open "$DEST"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$DEST"
fi
