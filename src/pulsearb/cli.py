from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path

import uvicorn

from pulsearb.branding import PRODUCT
from pulsearb.config import AppConfig
from pulsearb.engine.runner import Engine
from pulsearb.netutil import choose_port
from pulsearb.web.app import create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="securetrade",
        description=f"{PRODUCT}: scan 50+ crypto and FX markets on Coinbase, Kraken, Gemini, Bitstamp, and Yahoo. Paper trading by default.",
    )
    parser.add_argument("--host", help="Dashboard bind host (default 127.0.0.1). Use 0.0.0.0 for iPad on Wi-Fi; the lock PIN is required.")
    parser.add_argument("--port", type=int, help="Dashboard port")
    parser.add_argument("--demo", action="store_true", help="Offline simulator only — no live APIs")
    parser.add_argument(
        "--live-trading",
        action="store_true",
        help="Send real Coinbase orders. Requires keys/coinbase.json and PULSEARB_LIVE_CONFIRM=I_UNDERSTAND_THE_RISK",
    )
    parser.add_argument("--binance", action="store_true", help="Also enable Binance (not available to US residents)")
    parser.add_argument("--open-browser", action="store_true", help="Open the dashboard in a browser")
    parser.add_argument("--strict-port", action="store_true", help="Fail if the requested port is busy instead of trying the next one")
    parser.add_argument("--markets", type=Path, help="Optional markets.yaml override")
    parser.add_argument("--settings", type=Path, help="Optional settings.yaml override")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    config = AppConfig(markets_path=args.markets, settings_path=args.settings)
    if args.binance:
        config.env.enable_binance = True
        config._apply_env_overrides()
    if args.demo:
        config.env.demo_only = True
        config._apply_env_overrides()
    if args.live_trading and args.demo:
        raise SystemExit("Cannot combine --demo and --live-trading.")
    if args.live_trading:
        config.settings.setdefault("execution", {})["mode"] = "live"
    if args.host:
        config.settings["host"] = args.host
    if args.port:
        config.settings["port"] = args.port
    requested = config.port
    if args.strict_port:
        port = requested
    else:
        port = choose_port(config.host, requested)
        if port != requested:
            print(
                f"{PRODUCT}: port {requested} is already in use "
                f"(another SecureTrade window may still be open). Using port {port} instead."
            )
    config.settings["port"] = port
    engine = Engine(config)
    if args.live_trading and not config.live_enabled():
        raise SystemExit(
            "Live trading is not armed.\n"
            "1. Save the Coinbase API JSON as keys/coinbase.json (see LIVE.txt)\n"
            "2. Set PULSEARB_LIVE_CONFIRM=I_UNDERSTAND_THE_RISK\n"
            "Or double-click GO-LIVE.bat"
        )
    app = create_app(engine, start_engine=True)
    display_host = "127.0.0.1" if config.host in {"0.0.0.0", "::"} else config.host
    url = f"http://{display_host}:{port}"
    guard = app.state.guard
    print(f"{PRODUCT} dashboard: {url}")
    print(f"{PRODUCT} lock PIN: {guard.pin}")
    print(f"{PRODUCT}: this computer's browser unlocks automatically.")
    print(f"{PRODUCT}: phone or iPad — type that PIN on the lock screen.")
    if engine.report.csv_path:
        print(f"{PRODUCT} profit report: {engine.report.csv_path}")
    if config.live_enabled():
        venues = ", ".join(config.live_venue_names()) or "none"
        print(f"{PRODUCT} LIVE TRADING ON ({venues}). Real market orders.")
        print(f"{PRODUCT} live cap: ${config.live_notional():.0f} per trade. Cross-venue stays paper.")
        print("A failed live leg trips the kill switch. Close this window to stop.")
    print("Leave this window open. Close it or press Ctrl+C to stop.")
    if args.open_browser:
        webbrowser.open(f"{url}?unlock={guard.unlock_token}")
    uvicorn.run(app, host=config.host, port=port, log_level="info")


if __name__ == "__main__":
    main()
