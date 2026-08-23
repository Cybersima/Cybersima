# CyberSym SecureTrade

**CyberSym SecureTrade** is CyberSym’s retail-friendly crypto + FX dislocation scanner. It watches 50+ markets at once across **Coinbase, Kraken, Gemini, OANDA, and Robinhood**, flags cross-venue and triangular gaps, and paper-trades executable legs by default. Live orders stay off until you opt in. Yahoo (delayed) and Bitstamp (Robinhood merger, retail close-only Feb 2027) stay off the desk.

A CyberSym product. Binance is **disabled by default** because it is not available to US residents. You can turn it on with `--binance` if you are in a supported region.

This is a scanner with hard risk limits. Public APIs are not an HFT pipe. You will not outrun professional market makers, and nothing here is a profit guarantee or financial advice.

## Download and install on your computer

**This zip is the installer.** Unzip it on your PC and run `INSTALL.bat`. You do not need GitHub.

**Versions 1.4 and 1.5 are withdrawn.** They broke Windows Python (`No module named encodings`). Unzip into a new folder. Do not copy `.venv` from 1.4 or 1.5.

You need [Python 3.11+](https://www.python.org/downloads/). On Windows, tick **Add python.exe to PATH**.

If several Python versions are installed, SecureTrade uses **`C:\Python314\python.exe` first** (not `py -3`, which picks a random version). To force a different copy, put one line in `python-path.txt` next to `start.bat`:

`C:\Python314\python.exe`

Unzip into a **new** folder. Do not copy `.venv` from 1.4 or 1.5.

1. Download and unzip `CyberSym-SecureTrade.zip`.
2. Install, then start:
   - **Windows:** double-click `INSTALL.bat`, then `start.bat`
   - **Mac:** double-click `Install.command`, then `start.command` (right-click → Open if macOS blocks it)
   - **Linux:** `./install.sh && ./start.sh`
3. Open [http://127.0.0.1:8080](http://127.0.0.1:8080) (or 8081+ if 8080 is already in use).

If Windows says the port is already in use, close the other black SecureTrade window and start again. The latest build also tries 8081, 8082, and so on automatically.

That first run is **demo / paper trading**. No API keys, no real orders. Close the terminal window to stop.

See `DOWNLOAD.txt` in the zip for the same steps.

On the dashboard, set **How much per tap** ($1–$5 typical), choose coins and exchanges, then tap **Invest** on a trade (or turn on Auto in paper). Use **Show pairs** to keep only coins under (or over) a dollar amount, for example under $5. Coins priced under $1 still buy a fraction of a coin.

Your official crest: Windows **Install-Logo.bat** (same as Use-This-Logo.bat) picks a PNG/JPG and copies it to `branding/`. Then hard-refresh (Ctrl+F5). You do not need to restart.

The profit/trades spreadsheet is written to `data/CyberSym-SecureTrade-profit-report.csv`. Dashboard **Export report** downloads that file. Columns include ID, Detected Time, Strategy, Market, Route, Expected/Realized P&L, venues, raw/net edge, fees, slippage, fill ratio, and Paper Notional.

To rebuild a zip locally: `bash scripts/make-zip.sh`

## What it does

- **Coinbase Exchange** public REST + WebSocket tickers (no API key for market data)
- **Kraken and Gemini** public REST tickers
- **OANDA** FX (needs `keys/oanda.json`; start on practice)
- **Robinhood** crypto (needs `keys/robinhood.json`; no sandbox)
- **Cross-venue gaps** between those US venues (executable in paper mode)
- **Triangular arb** inside a single venue (e.g. BTC / ETH / USD on Coinbase or Kraken)
- **Paper broker** by default, with a kill switch, notional cap, cooldown, and daily loss limit
- **iPad / tablet dashboard** at `http://<this-machine>:8080` (PWA-capable, large blotter, Add to Home Screen)
- **Binance** remains optional (`python -m pulsearb --binance`) for non-US users

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m pulsearb --demo
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080). `--demo` uses a local simulator so the blotter works without network keys.

Live market data (still paper trading):

```bash
python -m pulsearb
```

On an iPad on the same Wi-Fi, start with `--host 0.0.0.0`, open `http://<your-lan-ip>:8080`, and enter the lock PIN from the black window. Then use Share → Add to Home Screen.

## Configuration

| File | Role |
| --- | --- |
| `src/pulsearb/config/markets.yaml` | Symbols per venue (Coinbase, Kraken, Gemini, OANDA, Robinhood; Binance optional) |
| `src/pulsearb/config/settings.yaml` | Scan rate, fees, edge thresholds, risk caps |
| `.env.example` | Bind address, execution mode, Coinbase/Binance keys |

Copy `.env.example` to `.env` if you need to change host/port or enable live orders.

US exchange tickers refresh about once per second. Coinbase also has a WebSocket.

## Live execution (opt-in Coinbase)

`start-live.bat` / `./start.sh --live` is **live market data with paper fills**. Paper and live share that dashboard: switch **Paper / Live** when the ready check is green. You can switch back to Paper without restarting. `GO-LIVE.bat` still starts already live if you prefer.

Real Coinbase orders need a **Secret API key** at [portal.cdp.coinbase.com/projects/api-keys](https://portal.cdp.coinbase.com/projects/api-keys) (View + Trade, no Transfer, ECDSA). In the popup click **Download API key**, save as `keys/coinbase.json`. Read `LIVE.txt` and run **CHECK-LIVE.bat** first.

Live mode:

- Sends **Coinbase dislocations** (same coin on the USD book vs the USDC book) and Coinbase triangles as market IOC orders: buy with USD, then sell, aiming to finish back in **USD**
- Default tap size **$5** (buttons from $0.10). Max **$25** per tap. Exchange pair mins still apply.
- Session live budget **$25** (split across many taps)
- Does **not** take cross-venue live (Coinbase vs Kraken/Gemini/Robinhood) — that would mean holding a coin to move it
- Keeps **Auto off** so every live order is a tap
- P&L is from actual fill prices
- Requires `PULSEARB_LIVE_CONFIRM=I_UNDERSTAND_THE_RISK` (GO-LIVE sets this)
- Pauses new orders if leftover coins from that tap cannot be sold back to USD

You can lose money. Optional Binance live orders (non-US) still require `--binance`, keys, live mode, and the confirm phrase.

## Package for a laptop

```bash
pip install .
securetrade --demo
```

Docker:

```bash
docker build -t cybersym-securetrade .
docker run --rm -p 8080:8080 cybersym-securetrade
```

## Tests

```bash
pytest
```

## Honest limits

- Retail Python + public exchange APIs is **seconds**, not microseconds.
- Cross-venue “gaps” are often stale or untradeable. Live cannot move coins between exchanges.
- Fees, slippage, and withdraw/deposit time usually eat cross-venue crypto/FX differences.
- 24/7 means **you** keep the process running (systemd, Docker, or a small VPS).

---

CyberSym SecureTrade · A CyberSym product · © CyberSym. All rights reserved.
