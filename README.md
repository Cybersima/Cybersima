# CyberSym SecureTrade 2

**Intelligent enough to find the opportunity. Secure enough to know when to walk away.**

SecureTrade 2 is a packaged product, not a folder of scripts. You install it, launch the command center, and a separate 24/7 engine keeps running even if the laptop sleeps.

Paper trading is the default. Live trading cannot be turned on until exchange connectivity, security configuration, risk limits, and safety checks pass.

## What you get

```
CyberSym SecureTrade 2
├── SecureTrade Desktop (command center)
├── Setup Wizard
├── Exchange Connector Manager
├── Market Scanner
├── Security & Fraud Engine
├── Arbitrage Engine
├── CyberSym Guardian™
├── Risk / Capital-protection Engine
├── Paper Lab (CAPTURED / REVERSED / MISSED / EXPIRED)
├── Live Trading Controller (gated)
├── Portfolio / P&L Dashboard
├── Alerts & Notifications
├── Audit / Decision Journal
├── Emergency Kill Switch (customer, risk, admin)
└── Secure Cloud Trading Engine (Docker)
```

## Architecture

The installed desktop app is the **command center**: setup, monitoring, controls, logs, and emergency shutdown.

The **engine** is designed to run independently (this machine or a VPS via Docker):

```
SCAN → DETECT → VERIFY → SECURITY SCREEN → RISK SCORE → SIMULATE
     → HANDOFF ATOMIC_READY → Final Commit (COMMIT | RESEARCH_COMMIT | CANCEL)
     → Paper Lab → CAPTURED | REVERSED | MISSED | EXPIRED
```

Final Commit is an advisory/measurement gate. `CANCEL` never enters Paper Lab.

## Operating modes

| Mode | Behavior |
|---|---|
| **Learn** | Simulated money and explanations (default) |
| **Assist** | Finds opportunities; you approve |
| **Auto** | Executes only inside customer-defined limits. Off on the Starter ladder. |

## Starter ladder (everyone can start)

| Rung | What it is |
|---|---|
| **Learn · $10** | Simulated $10. See expected cents. Not live. |
| **Learn · $100** | Recommended first step. Simulated $100. A 0.31% capture is about $0.31. |
| **Paper · $100** | Same $100 ticket through Paper Lab. Still simulated. |
| **Micro live · $100** | First live floor after paper. $100 max ticket, $5 daily loss, Auto off. |

Live $10 is not offered: exchange fees would dominate. **View Details** shows expected profit in dollars, fees, slippage, and why Guardian allowed or blocked the trade — not source code.


## Install

**Desktop (Windows / macOS / Linux)**

```bash
./install.sh
./start.sh          # or start.bat / start.command
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). On an iPad, add it to the Home Screen (PWA).

**24/7 engine (recommended for anything beyond a demo)**

```bash
docker compose up --build
```

Point the command center at the engine URL. Closing the laptop will not stop Docker/VPS trading.

## Safety

- Encrypted credential vault (`~/.cybersym/securetrade/credentials.enc`)
- Withdrawal-disabled trading keys by policy
- CyberSym Trust Score (0–100) and “Why this trade?” explanations
- Guardian can override the profit engine
- Daily loss, drawdown, allow-lists, and minimum net edge cannot be overridden by model confidence
- Multiple kill switches: customer, automated risk, health, admin
- Account-takeover detection suspends Auto mode
- Signed-update channel hook (`/api/updates`)
- Immutable-style decision journal

This is not a profit guarantee. Public APIs are not an HFT pipe. Yahoo is delayed. US default venues are Coinbase, Kraken, Gemini, and Bitstamp.

## Editions

Personal · Professional (multi-market) · Enterprise (managed, admin safety controls)

## Developers

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
python -m securetrade --demo
```

Recovery telemetry: [http://127.0.0.1:8000/api/recovery-commit](http://127.0.0.1:8000/api/recovery-commit)

© CyberSym. All rights reserved. A CyberSym product.
