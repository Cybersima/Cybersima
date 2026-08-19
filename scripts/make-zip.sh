#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "$ROOT/scripts/make_zip.py" "${1:-$ROOT/releases/CyberSym-SecureTrade.zip}"
