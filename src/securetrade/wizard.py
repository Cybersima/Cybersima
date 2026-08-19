from __future__ import annotations

from pathlib import Path

CONFIG_DIR = Path.home() / ".cybersym" / "securetrade"
WIZARD_FLAG = CONFIG_DIR / "first_run_complete"


def needs_wizard() -> bool:
    return not WIZARD_FLAG.exists()


def mark_complete() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    WIZARD_FLAG.write_text("ok\n", encoding="utf-8")


STEPS = [
    {"id": "welcome", "title": "Welcome", "body": "CyberSym SecureTrade 2 is a command center plus a 24/7 engine. Paper trading is the default."},
    {"id": "mode", "title": "Choose a mode", "body": "Learn (simulated money + explanations), Assist (approve every trade), or Auto (within your limits)."},
    {"id": "exchanges", "title": "Exchange connectors", "body": "Connect Coinbase, Kraken, Gemini, or Bitstamp with withdrawal-disabled keys. Binance is optional and off for US residents."},
    {"id": "security", "title": "Security", "body": "Enable MFA/passkeys, encrypt credentials, and keep withdrawals disabled. Guardian will refuse live mode until these pass."},
    {"id": "risk", "title": "Capital protection", "body": "Set max trade size, daily loss, drawdown, allowed assets, and minimum net edge. The bot cannot override these."},
    {"id": "engine", "title": "Where the engine runs", "body": "Keep the engine on this computer, or deploy the Docker cloud/VPS image so trading continues when the laptop sleeps."},
]
