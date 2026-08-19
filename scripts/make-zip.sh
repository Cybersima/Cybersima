#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/PulseArb.zip}"
exec python3 "$ROOT/scripts/make_zip.py" "$OUT"
