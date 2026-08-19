# PulseArb

Retail-friendly **crypto + FX dislocation scanner**. It watches 50+ markets at once, flags cross-venue and triangular gaps, and can paper-trade executable Binance legs. Live orders stay off until you opt in.

This is a scanner with hard risk limits. Public APIs are not an HFT pipe. Yahoo Finance is delayed. You will not outrun professional market makers, and nothing here is a profit guarantee or financial advice.

## Download and run on your computer

You need [Python 3.11+](https://www.python.org/downloads/) (Windows: tick **Add python.exe to PATH**).

1. Download the zip: [PulseArb.zip](https://github.com/Cybersima/Cybersima/archive/refs/heads/cursor/pulsearb-multimarket-scanner-c11f.zip)
2. Unzip it.
3. Open `START_HERE.txt`, then:
   - **Windows:** double-click `start.bat`
   - **Mac:** double-click `start.command` (right-click → Open if macOS blocks it)
   - **Linux:** `chmod +x start.sh && ./start.sh`
4. Open [http://127.0.0.1:8080](http://127.0.0.1:8080) if the browser does not open on its own.

That first run is **demo / paper trading**. No API keys, no real orders. Close the terminal window to stop.

To rebuild a zip locally: `bash scripts/make-zip.sh`

## What it does

- **Binance** public REST + WebSocket `bookTicker` for 50+ spot pairs (no API key for market data)
- **Yahoo Finance** for FX, metals, and overlapping crypto indices (data only — not executable)
- **Triangular arb** on Binance-style books (e.g. BTC / ETH / USDT)
- **Cross-venue alerts** when Binance and Yahoo disagree on the same asset
- **Paper broker** by default, with a kill switch, notional cap, cooldown, and daily loss limit
- **iPad / tablet dashboard** at `http://<this-machine>:8080` (PWA-capable, large blotter, Add to Home Screen)

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
| `src/pulsearb/config/markets.yaml` | Symbols (Binance + Yahoo) and cross-venue pairs |
| `src/pulsearb/config/settings.yaml` | Scan rate, fees, edge thresholds, risk caps |
| `.env.example` | Bind address, execution mode, Binance keys |

Copy `.env.example` to `.env` if you need to change host/port or enable live orders.

Yahoo is polled about every 2s on purpose. Hammering it at 1 Hz per ticker gets you blocked. Binance can update near once per second (REST watchdog) and faster over WebSocket.

## Live execution (opt-in)

Live Binance orders require **all** of:

1. `PULSEARB_EXECUTION_MODE=live`
2. `BINANCE_API_KEY` / `BINANCE_API_SECRET`
3. `PULSEARB_LIVE_CONFIRM=I_UNDERSTAND_THE_RISK`

Yahoo legs are never sent as orders. Alerts stay alerts. Start on **testnet** (`BINANCE_TESTNET=1`) if you experiment at all. You can lose money.

## Package for a laptop

```bash
pip install .
pulsearb --demo
```

Docker:

```bash
docker build -t pulsearb .
docker run --rm -p 8080:8080 pulsearb
```

## Tests

```bash
pytest
```

## Honest limits

- Retail Python + Yahoo + Binance public data is **seconds**, not microseconds.
- Many “gaps” vs Yahoo are stale data, not free money.
- Fees, slippage, and withdraw/deposit time usually eat cross-venue crypto/FX differences.
- 24/7 means **you** keep the process running (systemd, Docker, or a small VPS).
