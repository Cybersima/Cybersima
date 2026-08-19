@echo off
cd /d "%~dp0"
if not exist .venv (
  py -3 -m venv .venv
  .venv\Scripts\python -m pip install -U pip
  .venv\Scripts\pip install -e .
)
echo Starting CyberSym SecureTrade 2 on http://127.0.0.1:8000
.venv\Scripts\python -m securetrade desktop --demo --host 127.0.0.1 --port 8000
