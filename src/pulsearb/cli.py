from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from pulsearb.config import AppConfig
from pulsearb.engine.runner import Engine
from pulsearb.web.app import create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pulsearb",
        description="Scan 50+ crypto and FX markets for dislocations. Paper trading by default.",
    )
    parser.add_argument("--host", help="Dashboard bind host (default 0.0.0.0 for LAN / iPad)")
    parser.add_argument("--port", type=int, help="Dashboard port")
    parser.add_argument("--demo", action="store_true", help="Offline simulator only — no live APIs")
    parser.add_argument("--markets", type=Path, help="Optional markets.yaml override")
    parser.add_argument("--settings", type=Path, help="Optional settings.yaml override")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    config = AppConfig(markets_path=args.markets, settings_path=args.settings)
    if args.demo:
        config.env.demo_only = True
        config._apply_env_overrides()
    if args.host:
        config.settings["host"] = args.host
    if args.port:
        config.settings["port"] = args.port
    engine = Engine(config)
    app = create_app(engine, start_engine=True)
    uvicorn.run(app, host=config.host, port=config.port, log_level="info")


if __name__ == "__main__":
    main()
