from __future__ import annotations

from dataclasses import dataclass, field

from pulsearb.models import Opportunity, OpportunityKind
from pulsearb.symbols import split_pair

POPULAR_ASSETS = [
    "BTC",
    "ETH",
    "SOL",
    "XRP",
    "ADA",
    "DOGE",
    "LTC",
    "LINK",
    "AVAX",
    "DOT",
    "UNI",
    "AAVE",
]
QUOTE_SKIP = {"USD", "USDT", "USDC", "EUR", "GBP", "DAI"}
VENUES = ["coinbase", "kraken", "gemini", "bitstamp"]
KINDS = ["cross_venue", "triangular"]
KIND_LABELS = {
    "cross_venue": "Price gaps",
    "triangular": "Same-exchange triangles",
    "alert": "Watch only",
}
VENUE_LABELS = {
    "coinbase": "Coinbase",
    "kraken": "Kraken",
    "gemini": "Gemini",
    "bitstamp": "Bitstamp",
}


def opportunity_assets(opportunity: Opportunity) -> set[str]:
    found: set[str] = set()
    for leg in opportunity.legs:
        try:
            base, quote = split_pair(leg.symbol)
        except ValueError:
            continue
        for asset in (base, quote):
            if asset not in QUOTE_SKIP:
                found.add(asset)
    return found


@dataclass
class TradeDesk:
    """Customer choices: size, auto vs pick, coins, exchanges, trade style."""

    notional: float = 5.0
    auto_invest: bool = False
    all_assets: bool = False
    assets: list[str] = field(default_factory=lambda: ["BTC", "ETH", "SOL", "XRP"])
    venues: list[str] = field(default_factory=lambda: list(VENUES))
    kinds: list[str] = field(default_factory=lambda: list(KINDS))
    max_notional: float = 250.0
    live_max: float = 25.0
    min_notional: float = 1.0
    live: bool = False

    @property
    def cap(self) -> float:
        return min(self.max_notional, self.live_max) if self.live else self.max_notional

    def clamp_notional(self, value: float) -> float:
        try:
            amount = float(value)
        except (TypeError, ValueError):
            amount = self.notional
        floor = max(0.01, float(self.min_notional))
        return round(max(floor, min(amount, self.cap)), 2)

    def presets(self) -> list[float]:
        raw = [1, 2, 3, 4, 5, 10, 25] if self.live else [1, 2, 3, 4, 5, 10, 25, 50, 100]
        out: list[float] = []
        for item in raw:
            if self.min_notional - 1e-9 <= item <= self.cap + 1e-9:
                out.append(int(item) if float(item) == int(item) else float(item))
        cap_value = int(self.cap) if float(self.cap) == int(self.cap) else round(self.cap, 2)
        if cap_value not in out:
            out.append(cap_value)
        return out

    def apply(self, payload: dict) -> None:
        if "notional" in payload:
            self.notional = self.clamp_notional(payload.get("notional"))
        if "auto_invest" in payload:
            self.auto_invest = bool(payload.get("auto_invest"))
        if self.live:
            self.auto_invest = False
        if "all_assets" in payload:
            self.all_assets = bool(payload.get("all_assets"))
        if "assets" in payload:
            picked = [str(item).upper() for item in payload.get("assets") or []]
            self.assets = [item for item in picked if item in POPULAR_ASSETS]
            if not self.assets:
                self.all_assets = True
        if "venues" in payload:
            picked = [str(item).lower() for item in payload.get("venues") or []]
            self.venues = [item for item in VENUES if item in picked] or list(VENUES)
        if "kinds" in payload:
            picked = [str(item) for item in payload.get("kinds") or []]
            self.kinds = [item for item in KINDS if item in picked] or list(KINDS)

    def matches(self, opportunity: Opportunity) -> bool:
        if opportunity.kind == OpportunityKind.ALERT:
            return self._assets_ok(opportunity)
        if opportunity.kind.value not in self.kinds:
            return False
        needed = {
            leg.venue
            for leg in opportunity.legs
            if leg.venue not in {"yahoo", "simulator"}
        }
        if needed and not needed.issubset(set(self.venues)):
            return False
        return self._assets_ok(opportunity)

    def _assets_ok(self, opportunity: Opportunity) -> bool:
        if self.all_assets:
            return True
        wanted = {item.upper() for item in self.assets}
        coins = opportunity_assets(opportunity)
        if not coins:
            return True
        return bool(coins & wanted)

    def to_dict(self) -> dict:
        return {
            "notional": self.notional,
            "auto_invest": self.auto_invest,
            "auto_allowed": not self.live,
            "all_assets": self.all_assets,
            "assets": list(self.assets),
            "venues": list(self.venues),
            "kinds": list(self.kinds),
            "cap": self.cap,
            "live": self.live,
            "min_notional": self.min_notional,
            "presets": self.presets(),
            "asset_choices": list(POPULAR_ASSETS),
            "venue_choices": [{"id": item, "label": VENUE_LABELS[item]} for item in VENUES],
            "kind_choices": [{"id": item, "label": KIND_LABELS[item]} for item in KINDS],
        }
