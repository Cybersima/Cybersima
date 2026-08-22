from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from securetrade.models import OperatingMode


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

    host: str | None = Field(default=None, alias="SECURETRADE_HOST")
    port: int | None = Field(default=None, alias="SECURETRADE_PORT")
    execution_mode: str | None = Field(default=None, alias="SECURETRADE_EXECUTION_MODE")
    operating_mode: str | None = Field(default=None, alias="SECURETRADE_OPERATING_MODE")
    live_confirm: str = Field(default="", alias="SECURETRADE_LIVE_CONFIRM")
    edition: str | None = Field(default=None, alias="SECURETRADE_EDITION")
    engine_url: str = Field(default="", alias="SECURETRADE_ENGINE_URL")
    binance_api_key: str = Field(default="", alias="BINANCE_API_KEY")
    binance_api_secret: str = Field(default="", alias="BINANCE_API_SECRET")
    binance_testnet: bool = Field(default=False, alias="BINANCE_TESTNET")
    enable_binance: bool = Field(default=False, alias="SECURETRADE_ENABLE_BINANCE")
    demo_only: bool = Field(default=False, alias="SECURETRADE_DEMO_ONLY")
    # Keep PulseArb aliases so existing launchers still work.
    pulse_host: str | None = Field(default=None, alias="PULSEARB_HOST")
    pulse_port: int | None = Field(default=None, alias="PULSEARB_PORT")
    pulse_execution_mode: str | None = Field(default=None, alias="PULSEARB_EXECUTION_MODE")
    pulse_live_confirm: str = Field(default="", alias="PULSEARB_LIVE_CONFIRM")
    pulse_enable_binance: bool = Field(default=False, alias="PULSEARB_ENABLE_BINANCE")
    pulse_demo_only: bool = Field(default=False, alias="PULSEARB_DEMO_ONLY")


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
        host = self.env.host or self.env.pulse_host
        port = self.env.port or self.env.pulse_port
        execution = self.env.execution_mode or self.env.pulse_execution_mode
        if host:
            self.settings["host"] = host
        if port:
            self.settings["port"] = int(port)
        if execution:
            self.settings.setdefault("execution", {})["mode"] = execution.lower()
        if self.env.operating_mode:
            self.settings["operating_mode"] = self.env.operating_mode.lower()
        if self.env.edition:
            self.settings["edition"] = self.env.edition.lower()
        if self.env.enable_binance or self.env.pulse_enable_binance:
            self.markets.setdefault("binance", {})["enabled"] = True
        if self.env.demo_only or self.env.pulse_demo_only:
            for venue in LIVE_FEEDS:
                self.markets.setdefault(venue, {})["enabled"] = False
            self.settings.setdefault("simulator", {})["enabled"] = True

    @property
    def host(self) -> str:
        return str(self.settings.get("host", "0.0.0.0"))

    @property
    def port(self) -> int:
        return int(self.settings.get("port", 8000))

    @property
    def scan_interval_ms(self) -> int:
        return int(self.settings.get("scan_interval_ms", 250))

    @property
    def execution_mode(self) -> str:
        return str(self.settings.get("execution", {}).get("mode", "paper")).lower()

    @property
    def operating_mode(self) -> OperatingMode:
        raw = str(self.settings.get("operating_mode", "learn")).lower()
        try:
            return OperatingMode(raw)
        except ValueError:
            return OperatingMode.LEARN

    @property
    def edition(self) -> str:
        return str(self.settings.get("edition", "professional")).lower()

    @property
    def live_confirm_phrase(self) -> str:
        return str(self.settings.get("execution", {}).get("live_confirm_phrase", "I_UNDERSTAND_THE_RISK"))

    def venue_enabled(self, venue: str) -> bool:
        return bool((self.markets.get(venue) or {}).get("enabled"))

    def live_prerequisites(self) -> dict[str, bool]:
        security = self.settings.get("security") or {}
        risk = self.risk
        connectivity = any(self.venue_enabled(v) for v in SPOT_VENUES) or bool(
            (self.settings.get("simulator") or {}).get("enabled")
        )
        return {
            "paper_is_default": self.execution_mode == "paper",
            "exchange_connectivity": connectivity,
            "security_configuration": bool(security.get("mfa_required", True)),
            "risk_limits": bool(risk.get("daily_loss_limit_usdt") and risk.get("max_notional_usdt")),
            "safety_checks": bool(security.get("withdrawal_disabled", True)),
            "live_confirm": (self.env.live_confirm or self.env.pulse_live_confirm) == self.live_confirm_phrase,
            "api_keys": bool(self.env.binance_api_key and self.env.binance_api_secret),
            "binance_enabled": self.venue_enabled("binance"),
        }

    def live_enabled(self) -> bool:
        checks = self.live_prerequisites()
        return (
            self.execution_mode == "live"
            and checks["live_confirm"]
            and checks["api_keys"]
            and checks["binance_enabled"]
            and checks["security_configuration"]
            and checks["risk_limits"]
            and checks["safety_checks"]
            and checks["exchange_connectivity"]
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

    @property
    def capital(self) -> dict[str, Any]:
        return dict(self.settings.get("capital") or {})

    @property
    def guardian(self) -> dict[str, Any]:
        return dict(self.settings.get("guardian") or {})

    def fee_map(self) -> dict[str, float]:
        fees = self.fees
        mapping = {}
        for venue in (*SPOT_VENUES, "simulator", "yahoo"):
            mapping[venue] = float(fees.get(f"{venue}_taker_bps", fees.get("binance_taker_bps", 10)))
        return mapping

    @property
    def starting_equity(self) -> float:
        return float(self.settings.get("paper", {}).get("starting_equity", 25000))

    @property
    def forex(self) -> dict[str, Any]:
        return dict(self.settings.get("forex") or {})

    @property
    def yahoo_poll_seconds(self) -> float:
        yahoo = self.markets.get("yahoo") or {}
        if yahoo.get("poll_seconds") is not None:
            return float(yahoo.get("poll_seconds"))
        return float(self.settings.get("yahoo_poll_seconds", 3.0))
