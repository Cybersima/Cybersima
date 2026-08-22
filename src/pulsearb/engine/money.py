from __future__ import annotations

from pulsearb.models import Fill, Opportunity
from pulsearb.symbols import pair_asset_class, split_pair

STABLE = {"USD", "USDT", "USDC"}
CONVERT_TO_USD = {"USDC", "USDT"}


def taker_bps(fee_map: dict[str, float], venue: str, symbol: str) -> float:
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
            return float(fee_map.get("kraken_fx", 20.0))
        return float(fee_map.get(venue, 20.0))
    return float(fee_map.get(venue, 50.0))


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


def coinbase_live_ok(opportunity: Opportunity) -> bool:
    """True when every leg is Coinbase and the tap starts by buying with USD."""
    return venue_live_ok(opportunity, "coinbase")
