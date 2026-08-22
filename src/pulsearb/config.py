from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_MARKETS = PACKAGE_DIR / "config" / "markets.yaml"
DEFAULT_SETTINGS = PACKAGE_DIR / "config" / "settings.yaml"
SPOT_VENUES = ("coinbase", "kraken", "gemini", "bitstamp", "binance")
LIVE_FEEDS = SPOT_VENUES + ("yahoo",)


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    host: str | None = Field(default=None, alias="PULSEARB_HOST")
    port: int | None = Field(default=None, alias="PULSEARB_PORT")
    execution_mode: str | None = Field(default=None, alias="PULSEARB_EXECUTION_MODE")
    live_confirm: str = Field(default="", alias="PULSEARB_LIVE_CONFIRM")
    binance_api_key: str = Field(default="", alias="BINANCE_API_KEY")
    binance_api_secret: str = Field(default="", alias="BINANCE_API_SECRET")
    binance_testnet: bool = Field(default=False, alias="BINANCE_TESTNET")
    enable_binance: bool = Field(default=False, alias="PULSEARB_ENABLE_BINANCE")
    demo_only: bool = Field(default=False, alias="PULSEARB_DEMO_ONLY")
    coinbase_api_key: str = Field(default="", alias="COINBASE_API_KEY")
    coinbase_api_secret: str = Field(default="", alias="COINBASE_API_SECRET")
    coinbase_api_json: str = Field(default="", alias="COINBASE_API_JSON")
    kraken_api_key: str = Field(default="", alias="KRAKEN_API_KEY")
    kraken_api_secret: str = Field(default="", alias="KRAKEN_API_SECRET")
    kraken_api_json: str = Field(default="", alias="KRAKEN_API_JSON")


class AppConfig:
    def __init__(
        self,
        markets_path: Path | None = None,
        settings_path: Path | None = None,
    ) -> None:
        self.markets_path = markets_path or DEFAULT_MARKETS
        self.settings_path = settings_path or DEFAULT_SETTINGS
        self.markets = load_yaml(self.markets_path)
        self.settings = load_yaml(self.settings_path)
        self.env = EnvSettings()
        self._apply_env_overrides()

    def _apply_env_overrides(self) -> None:
        if self.env.host:
            self.settings["host"] = self.env.host
        if self.env.port:
            self.settings["port"] = int(self.env.port)
        if self.env.execution_mode:
            self.settings.setdefault("execution", {})["mode"] = self.env.execution_mode.lower()
        if self.env.enable_binance:
            self.markets.setdefault("binance", {})["enabled"] = True
        if self.env.demo_only:
            for venue in LIVE_FEEDS:
                self.markets.setdefault(venue, {})["enabled"] = False
            self.settings.setdefault("simulator", {})["enabled"] = True

    @property
    def host(self) -> str:
        return str(self.settings.get("host", "127.0.0.1"))

    @property
    def port(self) -> int:
        return int(self.settings.get("port", 8080))

    @property
    def scan_interval_ms(self) -> int:
        return int(self.settings.get("scan_interval_ms", 250))

    @property
    def execution_mode(self) -> str:
        return str(self.settings.get("execution", {}).get("mode", "paper")).lower()

    @property
    def live_confirm_phrase(self) -> str:
        return str(self.settings.get("execution", {}).get("live_confirm_phrase", "I_UNDERSTAND_THE_RISK"))

    def coinbase_credentials(self) -> tuple[str, str] | None:
        from pulsearb.engine.keys import load_coinbase_credentials

        return load_coinbase_credentials(
            cwd=Path.cwd(),
            json_path=self.env.coinbase_api_json or None,
            api_key=self.env.coinbase_api_key,
            api_secret=self.env.coinbase_api_secret,
        )

    def kraken_credentials(self) -> tuple[str, str] | None:
        from pulsearb.engine.keys import load_kraken_credentials

        return load_kraken_credentials(
            cwd=Path.cwd(),
            json_path=self.env.kraken_api_json or None,
            api_key=self.env.kraken_api_key,
            api_secret=self.env.kraken_api_secret,
        )

    def binance_live_ready(self) -> bool:
        return bool(
            self.venue_enabled("binance")
            and self.env.binance_api_key
            and self.env.binance_api_secret
        )

    def live_enabled(self) -> bool:
        if self.execution_mode != "live":
            return False
        if self.env.live_confirm != self.live_confirm_phrase:
            return False
        return (
            self.coinbase_credentials() is not None
            or self.kraken_credentials() is not None
            or self.binance_live_ready()
        )

    def live_notional(self) -> float:
        paper = float(self.risk.get("max_notional_usdt", 250))
        if not self.live_enabled():
            return paper
        live_cap = float(self.risk.get("live_max_notional_usdt", 25))
        return min(paper, live_cap)

    def live_venue_names(self) -> list[str]:
        names: list[str] = []
        if self.coinbase_credentials() is not None:
            names.append("coinbase")
        if self.kraken_credentials() is not None:
            names.append("kraken")
        if self.binance_live_ready():
            names.append("binance")
        return names

    def venue_enabled(self, venue: str) -> bool:
        return bool((self.markets.get(venue) or {}).get("enabled"))

    def symbols(self, venue: str) -> list[str]:
        return [str(item) for item in (self.markets.get(venue) or {}).get("symbols") or []]

    @property
    def binance_symbols(self) -> list[str]:
        return self.symbols("binance")

    @property
    def yahoo_symbols(self) -> list[dict[str, str]]:
        return list(self.markets.get("yahoo", {}).get("symbols") or [])

    @property
    def usd_equivalents(self) -> set[str]:
        return {item.upper() for item in self.markets.get("usd_equivalents") or []}

    @property
    def fees(self) -> dict[str, float]:
        raw = self.settings.get("fees") or {}
        return {str(k): float(v) for k, v in raw.items()}

    @property
    def risk(self) -> dict[str, float]:
        raw = self.settings.get("risk") or {}
        return {str(k): float(v) for k, v in raw.items()}

    def fee_map(self) -> dict[str, float]:
        fees = self.fees
        mapping = {}
        for venue in (*SPOT_VENUES, "simulator", "yahoo"):
            mapping[venue] = float(fees.get(f"{venue}_taker_bps", fees.get("binance_taker_bps", 10)))
        mapping["coinbase_stable"] = float(fees.get("coinbase_stable_taker_bps", 1.0))
        mapping["coinbase_maker"] = float(fees.get("coinbase_maker_bps", 40.0))
        mapping["kraken_fx"] = float(fees.get("kraken_fx_taker_bps", 20.0))
        mapping["kraken_maker"] = float(fees.get("kraken_maker_bps", 16.0))
        mapping["kraken_fx_maker"] = float(fees.get("kraken_fx_maker_bps", 16.0))
        return mapping

    def maker_exits(self) -> bool:
        return bool((self.settings.get("execution") or {}).get("maker_exits", True))

    def maker_wait_seconds(self) -> float:
        try:
            return max(0.0, float((self.settings.get("execution") or {}).get("maker_wait_seconds", 8)))
        except (TypeError, ValueError):
            return 8.0
