#!/usr/bin/env bash
# Double-click on macOS to install CyberSym SecureTrade.
cd "$(dirname "$0")" || exit 1
chmod +x install.sh start.sh start.command 2>/dev/null || true
./install.sh
echo
echo "Installed. Double-click start.command to run, or: ./start.sh"
read -r -p "Press Enter to close." _
