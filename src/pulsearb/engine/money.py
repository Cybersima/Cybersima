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


def replay_paper_pocket(
    fills: list[Fill],
    notional: float,
    start_quote: str = "USD",
) -> dict[str, float]:
    cash = start_quote if start_quote in STABLE else "USD"
    pocket: dict[str, float] = {cash: float(notional)}
    for fill in fills:
        if fill.status != "filled" or fill.qty <= 0:
            continue
        try:
            base, quote = split_pair(fill.symbol)
        except ValueError:
            continue
        spent = float(fill.notional or 0.0)
        if spent <= 0:
            spent = float(fill.qty) * float(fill.price)
        if fill.side == "buy":
            pocket[quote] = pocket.get(quote, 0.0) - spent
            pocket[base] = pocket.get(base, 0.0) + float(fill.qty)
        elif fill.side == "sell":
            pocket[base] = pocket.get(base, 0.0) - float(fill.qty)
            pocket[quote] = pocket.get(quote, 0.0) + spent
    return pocket


def _usd_mark(asset: str, fills: list[Fill]) -> float | None:
    for fill in reversed(fills):
        if fill.status != "filled" or fill.price <= 0:
            continue
        try:
            base, quote = split_pair(fill.symbol)
        except ValueError:
            continue
        if base == asset and quote in STABLE:
            return float(fill.price)
        if quote == asset and base in STABLE:
            return 1.0 / float(fill.price)
    return None


def mark_pocket_usd(pocket: dict[str, float], fills: list[Fill]) -> float:
    total = 0.0
    for asset, qty in pocket.items():
        if abs(qty) <= 1e-12:
            continue
        if asset in STABLE:
            total += qty
            continue
        px = _usd_mark(asset, fills)
        if px is not None:
            total += qty * px
    return total


def paper_tap_pnl(fills: list[Fill], notional: float, start_quote: str = "USD") -> float:
    """Paper round-trip: ending stables (plus leftover coin marked to USD) minus tap size.

    cash_pnl() only sees USD-quoted fills, so a $250 buy that exits into EUR/GBP/BTC
    prints as -250 even though the tap still holds that coin. Leftover coin that
    cannot be marked is treated as unrealized (0), not a cash loss of the tap.
    """
    size = float(notional)
    pocket = replay_paper_pocket(fills, size, start_quote)
    end = mark_pocket_usd(pocket, fills)
    leftover = any(abs(qty) > 1e-8 for asset, qty in pocket.items() if asset not in STABLE)
    if leftover and end < 0.5 * size:
        return 0.0
    return end - size


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


def oanda_roundtrip_ok(opportunity: Opportunity) -> bool:
    """OANDA live is open-then-close on one USD-quoted pair, not a triangle."""
    if not venue_live_ok(opportunity, "oanda"):
        return False
    legs = opportunity.legs
    return (
        len(legs) == 2
        and legs[0].action == "buy"
        and legs[1].action == "sell"
        and legs[0].symbol == legs[1].symbol
    )


def live_exec_ok(opportunity: Opportunity, venue: str) -> bool:
    """True when this venue's live broker can send the row as written."""
    wanted = str(venue or "").strip().lower()
    if wanted == "oanda":
        return oanda_roundtrip_ok(opportunity)
    return venue_live_ok(opportunity, wanted)


def auto_route_ok(opportunity: Opportunity, live_venue: str, *, live: bool) -> bool:
    """Auto only takes same-exchange USD-start routes that live can send.

    Cross-venue (Kraken vs Gemini, etc.) and USDC-first triangles stay
    click-to-paper so they cannot starve the real taps.
    Paper Auto stays Coinbase or Kraken so Gemini paper edges cannot starve
    the venues that actually go live most often.
    """
    if live:
        return live_exec_ok(opportunity, live_venue)
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
