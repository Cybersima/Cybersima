#!/usr/bin/env bash
cd "$(dirname "$0")" || exit 1
chmod +x check-live.sh 2>/dev/null || true
./check-live.sh
status=$?
echo
read -r -p "Press Enter to close." _
exit "$status"
