from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path

import uvicorn

from securetrade.branding import PRODUCT
from securetrade.config import AppConfig
from securetrade.engine.runner import Engine
from securetrade.web.app import create_app
from securetrade.wizard import needs_wizard


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="securetrade",
        description=f"{PRODUCT}: security-first trading intelligence. Command center + 24/7 engine. Paper by default.",
    )
    parser.add_argument("command", nargs="?", default="desktop", choices=["desktop", "engine", "wizard", "doctor", "package"])
    parser.add_argument("--host", help="Bind host (default 0.0.0.0 for LAN / iPad)")
    parser.add_argument("--port", type=int, help="API / dashboard port (default 8000)")
    parser.add_argument("--demo", action="store_true", help="Offline simulator only — no live APIs")
    parser.add_argument("--binance", action="store_true", help="Also enable Binance (not available to US residents)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the command center in a browser")
    parser.add_argument("--markets", type=Path, help="Optional markets.yaml override")
    parser.add_argument("--settings", type=Path, help="Optional settings.yaml override")
    return parser


def _config(args: argparse.Namespace) -> AppConfig:
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
    return config


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "package":
        from securetrade.packager import build_zip, package_info

        path = build_zip()
        info = package_info(path)
        print(path)
        print("sha256", info["sha256"])
        print("bytes", info["bytes"])
        return
    config = _config(args)
    if args.command == "doctor":
        from securetrade.updates import check_for_updates

        print(PRODUCT)
        print("edition:", config.edition)
        print("mode:", config.operating_mode.value)
        print("execution:", config.execution_mode)
        print("live_prerequisites:", config.live_prerequisites())
        print("updates:", check_for_updates())
        return
    engine = Engine(config)
    app = create_app(engine, start_engine=True)
    open_ui = args.command in {"desktop", "wizard"} and not args.no_browser
    if open_ui:
        path = "/setup" if args.command == "wizard" or needs_wizard() else "/"
        webbrowser.open(f"http://127.0.0.1:{config.port}{path}")
    uvicorn.run(app, host=config.host, port=config.port, log_level="info")


if __name__ == "__main__":
    main()
