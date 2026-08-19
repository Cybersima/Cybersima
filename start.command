#!/usr/bin/env bash
# Double-clickable on macOS. Same as start.sh.
cd "$(dirname "$0")" || exit 1
chmod +x start.sh 2>/dev/null || true
exec ./start.sh "$@"
