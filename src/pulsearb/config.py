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
        return str(self.settings.get("host", "0.0.0.0"))

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

    def venue_enabled(self, venue: str) -> bool:
        return bool((self.markets.get(venue) or {}).get("enabled"))

    def live_enabled(self) -> bool:
        return (
            self.execution_mode == "live"
            and self.env.live_confirm == self.live_confirm_phrase
            and bool(self.env.binance_api_key and self.env.binance_api_secret)
            and self.venue_enabled("binance")
        )

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
        return mapping
