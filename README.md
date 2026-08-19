# CyberSym SecureTrade

**CyberSym SecureTrade** is CyberSym’s retail-friendly crypto + FX dislocation scanner. It watches 50+ markets at once across **Coinbase, Kraken, Gemini, Bitstamp, and Yahoo Finance**, flags cross-venue and triangular gaps, and paper-trades executable legs by default. Live orders stay off until you opt in.

A CyberSym product. Binance is **disabled by default** because it is not available to US residents. You can turn it on with `--binance` if you are in a supported region.

This is a scanner with hard risk limits. Public APIs are not an HFT pipe. Yahoo Finance is delayed. You will not outrun professional market makers, and nothing here is a profit guarantee or financial advice.

## Download and install on your computer

**Installer zip (click to download):**  
https://github.com/Cybersima/Cybersima/raw/cursor/pulsearb-multimarket-scanner-c11f/releases/CyberSym-SecureTrade.zip

You need [Python 3.11+](https://www.python.org/downloads/). On Windows, tick **Add python.exe to PATH**.

1. Download and unzip `CyberSym-SecureTrade.zip`.
2. Install, then start:
   - **Windows:** double-click `INSTALL.bat`, then `start.bat`
   - **Mac:** double-click `Install.command`, then `start.command` (right-click → Open if macOS blocks it)
   - **Linux:** `./install.sh && ./start.sh`
3. Open [http://127.0.0.1:8080](http://127.0.0.1:8080) (or 8081+ if 8080 is already in use).

If Windows says the port is already in use, close the other black SecureTrade window and start again. The latest build also tries 8081, 8082, and so on automatically.

That first run is **demo / paper trading**. No API keys, no real orders. Close the terminal window to stop.

See `DOWNLOAD.txt` in the zip for the same steps.

On the dashboard, set **How much to invest**, choose coins and exchanges, then tap **Invest** on a trade (or turn on Auto).

Your official crest: save it as `branding/cybersym-logo.png` next to `start.bat`, then refresh (Ctrl+F5). Windows: **Use-This-Logo.bat** opens that folder.

The profit/trades spreadsheet is written to `data/CyberSym-SecureTrade-profit-report.csv`. Dashboard **Export report** downloads that file. Columns include ID, Detected Time, Strategy, Market, Route, Expected/Realized P&L, venues, raw/net edge, fees, slippage, fill ratio, and Paper Notional.

To rebuild a zip locally: `bash scripts/make-zip.sh`

## What it does

- **Coinbase Exchange** public REST + WebSocket tickers (no API key for market data)
- **Kraken, Gemini, and Bitstamp** public REST tickers
- **Yahoo Finance** for FX, metals, and overlapping crypto indices (data only — not executable)
- **Cross-venue gaps** between those US exchanges (executable in paper mode) and vs Yahoo (alerts only)
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

On an iPad on the same Wi-Fi, open `http://<your-lan-ip>:8080` and use Share → Add to Home Screen.

## Configuration

| File | Role |
| --- | --- |
| `src/pulsearb/config/markets.yaml` | Symbols per venue (Coinbase, Kraken, Gemini, Bitstamp, Yahoo; Binance optional) |
| `src/pulsearb/config/settings.yaml` | Scan rate, fees, edge thresholds, risk caps |
| `.env.example` | Bind address, execution mode, Coinbase/Binance keys |

Copy `.env.example` to `.env` if you need to change host/port or enable live orders.

Yahoo is polled about every 2s on purpose. US exchange tickers refresh about once per second. Coinbase also has a WebSocket.

## Live execution (opt-in Coinbase)

`start-live.bat` / `./start.sh --live` is **live market data with paper fills**.

Real Coinbase orders are a separate add-on. Read `LIVE.txt`, save the Coinbase Advanced Trade API JSON as `keys/coinbase.json` (View + Trade, no Transfer), then run **GO-LIVE.bat** (Mac: `Go-Live.command`, Linux: `./go-live.sh`).

Live mode:

- Sends **Coinbase-only** triangles as market IOC orders
- Caps size at `live_max_notional_usdt` (default **$25**)
- Leaves cross-venue (Coinbase vs Kraken/Gemini/Bitstamp) on **paper** — you cannot instantly move coins between exchanges
- Requires `PULSEARB_LIVE_CONFIRM=I_UNDERSTAND_THE_RISK` (GO-LIVE sets this)
- Trips the kill switch if a live order fails

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
- Many “gaps” vs Yahoo are stale data, not free money.
- Fees, slippage, and withdraw/deposit time usually eat cross-venue crypto/FX differences.
- 24/7 means **you** keep the process running (systemd, Docker, or a small VPS).

---

CyberSym SecureTrade · A CyberSym product · © CyberSym. All rights reserved.
