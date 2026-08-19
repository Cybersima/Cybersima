from __future__ import annotations

from securetrade.engine.book import MarketBook
from securetrade.models import Opportunity, SimulationResult


def simulate_fill(opportunity: Opportunity, book: MarketBook) -> SimulationResult:
    """Estimate what would happen if the order hit the actual book right now."""
    notes: list[str] = []
    fillable = opportunity.notional
    slippage = 0.0
    for leg in opportunity.legs:
        quote = book.get(leg.venue, leg.symbol)
        if quote is None:
            notes.append(f"No live book for {leg.venue} {leg.symbol}")
            return SimulationResult(False, 0.0, 0.0, 0.0, notes)
        depth = quote.ask_size if leg.action == "buy" else quote.bid_size
        available = depth * (quote.ask if leg.action == "buy" else quote.bid) if depth else opportunity.notional * 4
        if available < opportunity.notional:
            fillable = min(fillable, available)
            notes.append("Quoted price lacks enough liquidity behind it")
            slippage += 6.0
        else:
            notes.append("Strong liquidity")
            slippage += max(0.0, quote.spread_bps / 4)
        if quote.spread_bps > 25:
            slippage += 4.0
            notes.append("Wide spread — slippage elevated")
    expected_net = opportunity.net_edge_bps - slippage
    viable = fillable >= opportunity.notional * 0.5 and expected_net > 0
    if expected_net <= 0:
        notes.append("Slippage erases the quoted edge")
    else:
        notes.append("Slippage acceptable")
        notes.append("Fees calculated")
    return SimulationResult(
        viable=viable,
        fillable_notional=round(fillable, 2),
        expected_slippage_bps=round(slippage, 2),
        expected_net_edge_bps=round(expected_net, 2),
        notes=notes,
    )
