#!/usr/bin/env bash
set -euo pipefail
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -e ".[dev]"
echo "Installed CyberSym SecureTrade. Start with: .venv/bin/securetrade --demo"
