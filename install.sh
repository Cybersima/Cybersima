#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -e ".[dev]"
echo "Installed CyberSym SecureTrade 2."
echo "Command center:  .venv/bin/securetrade --demo"
echo "24/7 engine:     docker compose up --build"
