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
    {"id": "welcome", "title": "Welcome", "body": "CyberSym SecureTrade 2 is a command center plus a 24/7 engine. Everyone can start. Paper trading is the default."},
    {"id": "starter", "title": "Starter ladder", "body": "Learn with simulated $10 or $100. Then Paper $100. Micro live $100 is optional after paper. Auto stays off. Live $10 is not offered — fees would eat a $10 ticket."},
    {"id": "mode", "title": "Choose a mode", "body": "Learn (simulated money + explanations), Assist (approve every trade), or Auto (only after you leave Starter and set your own limits)."},
    {"id": "dollars", "title": "Read dollars, not just percents", "body": "A 0.31% edge on a $100 ticket is about 31 cents. View Details shows expected profit, fees, slippage, and max loss in dollars before anything is sent."},
    {"id": "exchanges", "title": "Exchange connectors", "body": "Connect Coinbase, Kraken, Gemini, or Bitstamp with withdrawal-disabled keys. Binance is optional and off for US residents."},
    {"id": "security", "title": "Security", "body": "Enable MFA/passkeys, encrypt credentials, and keep withdrawals disabled. Guardian will refuse live mode until these pass."},
    {"id": "risk", "title": "Capital protection", "body": "Starter caps the ticket at your rung ($10 or $100) and a small daily loss. The bot cannot override those limits."},
    {"id": "engine", "title": "Where the engine runs", "body": "Keep the engine on this computer, or deploy the Docker cloud/VPS image so trading continues when the laptop sleeps."},
]
