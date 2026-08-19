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
    parser.add_argument("--host", help="Dashboard bind host (default 0.0.0.0 for LAN / iPad)")
    parser.add_argument("--port", type=int, help="Dashboard port")
    parser.add_argument("--demo", action="store_true", help="Offline simulator only — no live APIs")
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
    app = create_app(engine, start_engine=True)
    display_host = "127.0.0.1" if config.host in {"0.0.0.0", "::"} else config.host
    url = f"http://{display_host}:{port}"
    print(f"{PRODUCT} dashboard: {url}")
    print("Leave this window open. Close it or press Ctrl+C to stop.")
    if args.open_browser:
        webbrowser.open(url)
    uvicorn.run(app, host=config.host, port=port, log_level="info")


if __name__ == "__main__":
    main()
