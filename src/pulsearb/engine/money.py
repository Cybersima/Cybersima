from __future__ import annotations

from pulsearb.models import Fill, Opportunity
from pulsearb.symbols import pair_asset_class, split_pair

STABLE = {"USD", "USDT", "USDC"}
CONVERT_TO_USD = {"USDC", "USDT"}


def taker_bps(fee_map: dict[str, float], venue: str, symbol: str) -> float:
    return fee_bps(fee_map, venue, symbol, maker=False)


def fee_bps(fee_map: dict[str, float], venue: str, symbol: str, *, maker: bool = False) -> float:
    try:
        base, quote = split_pair(symbol)
    except ValueError:
        return float(fee_map.get(venue, 50.0))
    if {base, quote} <= STABLE:
        if venue == "coinbase":
            return float(fee_map.get("coinbase_stable", 1.0))
        return 1.0
    if pair_asset_class(symbol) == "fx":
        if venue == "coinbase":
            return float(fee_map.get("coinbase_stable", 1.0))
        if venue == "kraken":
            if maker:
                return float(fee_map.get("kraken_fx_maker", fee_map.get("kraken_maker", 16.0)))
            return float(fee_map.get("kraken_fx", 20.0))
        return float(fee_map.get(venue, 20.0))
    if maker:
        if venue == "kraken":
            return float(fee_map.get("kraken_maker", 16.0))
        if venue == "coinbase":
            return float(fee_map.get("coinbase_maker", 40.0))
        return float(fee_map.get(venue, 50.0))
    return float(fee_map.get(venue, 50.0))


def venue_maker_bps(fee_map: dict[str, float], venue: str) -> float:
    if venue == "kraken":
        return float(fee_map.get("kraken_maker", 16.0))
    if venue == "coinbase":
        return float(fee_map.get("coinbase_maker", 40.0))
    return float(fee_map.get(venue, 50.0))


def route_fee_bps(fee_map: dict[str, float], legs: list) -> float:
    """Sell legs use maker fees — matches live exits. Buys stay taker."""
    total = 0.0
    for leg in legs:
        maker = str(getattr(leg, "action", "")).lower() == "sell"
        total += fee_bps(fee_map, getattr(leg, "venue", ""), getattr(leg, "symbol", ""), maker=maker)
    return total


def cash_pnl(fills: list[Fill]) -> float:
    """USD (and USDC/USDT) in minus out from filled legs."""
    delta = 0.0
    for fill in fills:
        if fill.status != "filled" or fill.qty <= 0:
            continue
        try:
            _base, quote = split_pair(fill.symbol)
        except ValueError:
            continue
        if quote not in STABLE:
            continue
        usd = float(fill.qty) * float(fill.price)
        if fill.side == "buy":
            delta -= usd
        elif fill.side == "sell":
            delta += usd
    return delta


def venue_live_ok(opportunity: Opportunity, venue: str) -> bool:
    """True when every leg is on that venue and the tap starts by buying with USD."""
    wanted = str(venue or "").strip().lower()
    if not wanted or not opportunity.executable or not opportunity.legs:
        return False
    if any(leg.venue != wanted or not leg.executable for leg in opportunity.legs):
        return False
    first = opportunity.legs[0]
    if first.action != "buy":
        return False
    try:
        _base, quote = split_pair(first.symbol)
    except ValueError:
        return False
    return quote == "USD"


def auto_route_ok(opportunity: Opportunity, live_venue: str, *, live: bool) -> bool:
    """Auto only takes same-exchange USD-start routes that live can send.

    Cross-venue (Kraken vs Gemini, etc.) and USDC-first triangles stay
    click-to-paper so they cannot starve the real taps.
    """
    if live:
        return venue_live_ok(opportunity, live_venue)
    venues = {leg.venue for leg in opportunity.legs}
    if len(venues) != 1:
        return False
    only = next(iter(venues))
    if only not in {"coinbase", "kraken"}:
        return False
    return venue_live_ok(opportunity, only)


def coinbase_live_ok(opportunity: Opportunity) -> bool:
    """True when every leg is Coinbase and the tap starts by buying with USD."""
    return venue_live_ok(opportunity, "coinbase")
