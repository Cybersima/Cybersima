#!/usr/bin/env bash
cd "$(dirname "$0")" || exit 1
chmod +x go-live.sh 2>/dev/null || true
exec ./go-live.sh "$@"
