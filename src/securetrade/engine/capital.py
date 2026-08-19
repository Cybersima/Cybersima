from __future__ import annotations

from dataclasses import dataclass

from securetrade.models import Opportunity
from securetrade.symbols import split_pair


@dataclass
class CapitalDecision:
    allowed: bool
    reason: str = ""


class CapitalProtection:
    """Customer limits the bot must never override, even when the model is confident."""

    def __init__(self, settings: dict) -> None:
        self.max_trade_size = float(settings.get("max_trade_size", 250))
        self.max_position_exposure = float(settings.get("max_position_exposure", 1000))
        self.max_daily_loss = float(settings.get("max_daily_loss", 150))
        self.max_drawdown_pct = float(settings.get("max_drawdown_pct", 5))
        self.allowed_assets = {str(a).upper() for a in settings.get("allowed_assets") or []}
        self.allowed_exchanges = {str(a).lower() for a in settings.get("allowed_exchanges") or []}
        self.min_net_edge_bps = float(settings.get("min_net_edge_bps", 8))
        self.open_exposure = 0.0
        self.daily_pnl = 0.0
        self.account_value = float(settings.get("account_value", settings.get("max_position_exposure", 100)))

    def record(self, pnl: float, exposure_delta: float = 0.0) -> None:
        self.daily_pnl += pnl
        self.open_exposure = max(0.0, self.open_exposure + exposure_delta)
        self.account_value = max(0.0, self.account_value + pnl)

    def allow(self, opportunity: Opportunity, *, confidence: float = 1.0) -> CapitalDecision:
        _ = confidence  # confidence never overrides customer limits
        if opportunity.notional > self.max_trade_size:
            return CapitalDecision(False, "trade size exceeds capital policy")
        if opportunity.notional > 0 and hasattr(self, "account_value") and self.account_value > 0:
            if opportunity.notional > self.account_value + 1e-9:
                return CapitalDecision(False, "trade size exceeds account value")
        if self.open_exposure + opportunity.notional > self.max_position_exposure:
            return CapitalDecision(False, "position exposure exceeds capital policy")
        if self.daily_pnl <= -abs(self.max_daily_loss):
            return CapitalDecision(False, "daily loss exceeds capital policy")
        if opportunity.net_edge_bps < self.min_net_edge_bps:
            return CapitalDecision(False, "net edge below minimum acceptable")
        if self.allowed_exchanges:
            for leg in opportunity.legs:
                if leg.venue.lower() not in self.allowed_exchanges and leg.venue.lower() != "paper":
                    return CapitalDecision(False, f"{leg.venue} is not an allowed exchange")
        if self.allowed_assets:
            for leg in opportunity.legs:
                try:
                    base, quote = split_pair(leg.symbol if "-" in leg.symbol or "/" in leg.symbol else opportunity.pair or leg.symbol)
                except ValueError:
                    continue
                if base not in self.allowed_assets or quote not in self.allowed_assets:
                    return CapitalDecision(False, f"{base}/{quote} is outside the allowed-asset list")
        return CapitalDecision(True)
