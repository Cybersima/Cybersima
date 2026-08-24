from __future__ import annotations

from dataclasses import dataclass, field

from pulsearb.engine.book import MarketBook
from pulsearb.engine.schedule import format_hhmm, window_open
from pulsearb.models import Opportunity, OpportunityKind, Quote
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
    "EUR",
    "GBP",
    "AUD",
    "JPY",
    "CAD",
    "CHF",
]
QUOTE_SKIP = {"USD", "USDT", "USDC", "DAI"}
USD_PRICE_QUOTES = ("USD", "USDT", "USDC", "FDUSD", "BUSD", "TUSD")
PRICE_MODES = ("any", "under", "over")
PRICE_PRESETS = [1, 2, 5, 10, 50, 100, 1000]
# Yahoo is delayed/watch-only. Bitstamp retail goes close-only Feb 2027
# (merging into Robinhood) — both stay off the tradable desk.
SITE_HIDDEN_VENUES = {"yahoo", "bitstamp"}
# Delayed / non-exchange feeds: book them for reference, never buy or sell.
DATA_ONLY_VENUES = {"yahoo"}
VENUES = ["coinbase", "kraken", "gemini", "oanda", "robinhood"]
KINDS = ["cross_venue", "dislocation", "triangular"]
KIND_LABELS = {
    "cross_venue": "Price gaps",
    "dislocation": "USD vs USDC dislocations",
    "triangular": "Same-exchange triangles",
    "alert": "Watch only",
}
LIVE_VENUES = ["coinbase", "kraken", "gemini", "oanda", "robinhood"]
VENUE_LABELS = {
    "coinbase": "Coinbase",
    "kraken": "Kraken",
    "gemini": "Gemini",
    "oanda": "OANDA",
    "robinhood": "Robinhood",
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


def coin_usd_price(book: MarketBook | None, coin: str, venue: str | None = None) -> float | None:
    """USD (or stablecoin) mid for a coin. Prefers the given venue, then any venue."""
    if book is None or not coin:
        return None
    coin = str(coin).upper()
    for quote in USD_PRICE_QUOTES:
        found = book.find_pair(coin, quote, venue=venue)
        if found is None and venue is not None:
            found = book.find_pair(coin, quote)
        if found is not None and found.mid > 0:
            return found.mid
    return None


@dataclass
class TradeDesk:
    """Customer choices: size, auto vs pick, coins, exchanges, trade style."""

    notional: float = 5.0
    auto_invest: bool = False
    all_assets: bool = False
    assets: list[str] = field(default_factory=lambda: ["BTC", "ETH", "SOL", "XRP", "EUR", "GBP"])
    venues: list[str] = field(default_factory=lambda: list(VENUES))
    kinds: list[str] = field(default_factory=lambda: list(KINDS))
    max_notional: float = 250.0
    live_max: float = 25.0
    min_notional: float = 1.0
    live: bool = False
    live_venue: str = "coinbase"
    schedule_enabled: bool = False
    schedule_start: str = "22:00"
    schedule_stop: str = "06:00"
    price_mode: str = "any"
    price_limit: float = 5.0
    min_price_limit: float = 0.01
    max_price_limit: float = 1_000_000.0

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
        raw = (
            [0.10, 0.25, 0.50, 1, 2, 3, 4, 5, 10, 25]
            if self.live
            else [0.10, 0.25, 0.50, 1, 2, 3, 4, 5, 10, 25, 50, 100]
        )
        out: list[float] = []
        for item in raw:
            if self.min_notional - 1e-9 <= item <= self.cap + 1e-9:
                out.append(int(item) if float(item) == int(item) else float(item))
        cap_value = int(self.cap) if float(self.cap) == int(self.cap) else round(self.cap, 2)
        if cap_value not in out:
            out.append(cap_value)
        return out

    def clamp_price_limit(self, value: float) -> float:
        try:
            amount = float(value)
        except (TypeError, ValueError):
            amount = self.price_limit
        floor = max(0.01, float(self.min_price_limit))
        ceiling = max(floor, float(self.max_price_limit))
        return round(max(floor, min(amount, ceiling)), 4)

    def apply(self, payload: dict) -> None:
        if "notional" in payload:
            self.notional = self.clamp_notional(payload.get("notional"))
        if "auto_invest" in payload:
            self.auto_invest = bool(payload.get("auto_invest"))
        if "live_venue" in payload:
            wanted = str(payload.get("live_venue") or "").strip().lower()
            if wanted in LIVE_VENUES:
                self.live_venue = wanted
        if "schedule_enabled" in payload:
            self.schedule_enabled = bool(payload.get("schedule_enabled"))
        if "schedule_start" in payload:
            self.schedule_start = format_hhmm(str(payload.get("schedule_start") or ""), "22:00")
        if "schedule_stop" in payload:
            self.schedule_stop = format_hhmm(str(payload.get("schedule_stop") or ""), "06:00")
        if self.live and not self.schedule_enabled:
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
        if "price_mode" in payload:
            mode = str(payload.get("price_mode") or "any").strip().lower()
            self.price_mode = mode if mode in PRICE_MODES else "any"
        if "price_limit" in payload:
            self.price_limit = self.clamp_price_limit(payload.get("price_limit"))

    def matches(self, opportunity: Opportunity, book: MarketBook | None = None) -> bool:
        if any(leg.venue in SITE_HIDDEN_VENUES for leg in opportunity.legs):
            return False
        if opportunity.kind == OpportunityKind.ALERT:
            return self._assets_ok(opportunity) and self._price_ok(opportunity, book)
        if opportunity.kind.value not in self.kinds:
            return False
        needed = {
            leg.venue
            for leg in opportunity.legs
            if leg.venue not in SITE_HIDDEN_VENUES | {"simulator"}
        }
        if needed and not needed.issubset(set(self.venues)):
            return False
        return self._assets_ok(opportunity) and self._price_ok(opportunity, book)

    def quote_ok(self, quote: Quote, book: MarketBook | None = None) -> bool:
        if quote.venue in SITE_HIDDEN_VENUES:
            return False
        if self.price_mode == "any":
            return True
        try:
            base, _quote = split_pair(quote.canonical or quote.native_symbol)
        except ValueError:
            return False
        return self._limit_ok(coin_usd_price(book, base, quote.venue))

    def _limit_ok(self, price: float | None) -> bool:
        if price is None or price <= 0:
            return False
        limit = self.price_limit
        if self.price_mode == "under":
            return price <= limit + 1e-12
        if self.price_mode == "over":
            return price >= limit - 1e-12
        return True

    def _price_ok(self, opportunity: Opportunity, book: MarketBook | None) -> bool:
        if self.price_mode == "any":
            return True
        coins = opportunity_assets(opportunity)
        if not coins:
            return False
        venues = [leg.venue for leg in opportunity.legs]
        for coin in coins:
            price = None
            for venue in venues:
                price = coin_usd_price(book, coin, venue)
                if price is not None:
                    break
            if not self._limit_ok(price):
                return False
        return True

    def _assets_ok(self, opportunity: Opportunity) -> bool:
        if self.all_assets:
            return True
        wanted = {item.upper() for item in self.assets}
        coins = opportunity_assets(opportunity)
        if not coins:
            return True
        return bool(coins & wanted)

    def schedule_active(self) -> bool:
        if not self.schedule_enabled:
            return True
        return window_open(self.schedule_start, self.schedule_stop)

    def auto_allowed(self) -> bool:
        if not self.live:
            return True
        return bool(self.schedule_enabled)

    def to_dict(self) -> dict:
        return {
            "notional": self.notional,
            "auto_invest": self.auto_invest,
            "auto_allowed": self.auto_allowed(),
            "all_assets": self.all_assets,
            "assets": list(self.assets),
            "venues": list(self.venues),
            "kinds": list(self.kinds),
            "cap": self.cap,
            "live": self.live,
            "live_venue": self.live_venue,
            "live_venue_choices": [{"id": item, "label": VENUE_LABELS[item]} for item in LIVE_VENUES],
            "schedule_enabled": self.schedule_enabled,
            "schedule_start": self.schedule_start,
            "schedule_stop": self.schedule_stop,
            "schedule_active": self.schedule_active(),
            "min_notional": self.min_notional,
            "presets": self.presets(),
            "asset_choices": list(POPULAR_ASSETS),
            "venue_choices": [{"id": item, "label": VENUE_LABELS[item]} for item in VENUES],
            "kind_choices": [{"id": item, "label": KIND_LABELS[item]} for item in KINDS],
            "price_mode": self.price_mode,
            "price_limit": self.price_limit,
            "price_presets": list(PRICE_PRESETS),
        }
