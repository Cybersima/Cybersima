# CyberSym SecureTrade

**CyberSym SecureTrade** is CyberSym’s retail-friendly crypto + FX dislocation scanner. It watches 50+ markets at once across **Coinbase, Kraken, Gemini, Bitstamp, and Yahoo Finance**, flags cross-venue and triangular gaps, and paper-trades executable legs by default. Live orders stay off until you opt in.

A CyberSym product. Binance is **disabled by default** because it is not available to US residents. You can turn it on with `--binance` if you are in a supported region.

This is a scanner with hard risk limits. Public APIs are not an HFT pipe. Yahoo Finance is delayed. You will not outrun professional market makers, and nothing here is a profit guarantee or financial advice.

## Download and run on your computer

You need [Python 3.11+](https://www.python.org/downloads/) (Windows: tick **Add python.exe to PATH**).

1. Download the zip: [CyberSym SecureTrade](https://github.com/Cybersima/Cybersima/archive/refs/heads/cursor/pulsearb-multimarket-scanner-c11f.zip)
2. Unzip it.
3. Open `START_HERE.txt`, then:
   - **Windows:** double-click `start.bat`
   - **Mac:** double-click `start.command` (right-click → Open if macOS blocks it)
   - **Linux:** `chmod +x start.sh && ./start.sh`
4. Open [http://127.0.0.1:8080](http://127.0.0.1:8080) if the browser does not open on its own.

That first run is **demo / paper trading**. No API keys, no real orders. Close the terminal window to stop.

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
| `.env.example` | Bind address, execution mode, optional Binance keys |

Copy `.env.example` to `.env` if you need to change host/port or enable live orders.

Yahoo is polled about every 2s on purpose. US exchange tickers refresh about once per second. Coinbase also has a WebSocket.

## Live execution (opt-in)

Paper trading is the default. Yahoo legs are never sent as orders.

Optional Binance live orders (non-US) require **all** of:

1. `PULSEARB_ENABLE_BINANCE=1` or `--binance`
2. `PULSEARB_EXECUTION_MODE=live`
3. `BINANCE_API_KEY` / `BINANCE_API_SECRET`
4. `PULSEARB_LIVE_CONFIRM=I_UNDERSTAND_THE_RISK`

You can lose money. Coinbase/Kraken/Gemini/Bitstamp live order routing is not wired up yet — those venues are for market data and paper fills.

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
