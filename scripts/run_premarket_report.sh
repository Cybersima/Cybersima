#!/usr/bin/env bash
# Wrapper for cron / launchd / Task Scheduler — 8:45 AM ET premarket report.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export TZ="${TZ:-America/New_York}"
mkdir -p "$ROOT/logs"
OUT="$ROOT/logs/premarket_$(date +%Y%m%d).txt"
# Prefer project venv if present
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY="python3"
else
  PY="python"
fi
cd "$ROOT"
"$PY" "$ROOT/scripts/premarket_report.py" --strict-premarket --out "$OUT" "$@"
echo "Report written to $OUT"
