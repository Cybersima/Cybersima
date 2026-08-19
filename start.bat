@echo off
cd /d "%~dp0"
set PYTHONHOME=
set PYTHONPATH=
if not exist .venv (
  py -3 -m venv .venv
  .venv\Scripts\python -m pip install -U pip
)
.venv\Scripts\python -m pip install -e . -q
echo Starting CyberSym SecureTrade 2 on http://127.0.0.1:8000
echo Paper trading is the default. Press Ctrl+C in this window to stop.
.venv\Scripts\python -m securetrade desktop --demo --host 127.0.0.1 --port 8000
