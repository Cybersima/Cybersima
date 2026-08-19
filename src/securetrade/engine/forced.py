from __future__ import annotations

import time

from securetrade.engine.book import MarketBook
from securetrade.models import Leg, Opportunity, OpportunityKind, Quote
from securetrade.symbols import canonical_from_pair


def make_quote(
    venue: str,
    symbol: str,
    bid: float,
    ask: float,
    executable: bool = True,
    size: float = 5.0,
    ts: float | None = None,
) -> Quote:
    canonical = symbol if "-" in symbol else canonical_from_pair(symbol)
    return Quote(
        venue=venue,
        native_symbol=symbol,
        canonical=canonical,
        bid=bid,
        ask=ask,
        ts=ts or time.time(),
        executable=executable,
        bid_size=size,
        ask_size=size,
        latency_ms=12.0,
    )


def seed_quality_book(book: MarketBook | None = None) -> MarketBook:
    book = book or MarketBook()
    now = time.time()
    book.update(make_quote("coinbase", "BTC-USD", 97000, 97010, size=8, ts=now))
    book.update(make_quote("kraken", "XBTUSD", 97320, 97340, size=6, ts=now))
    book.update(make_quote("gemini", "btcusd", 97110, 97130, size=5, ts=now))
    return book


def make_forced_opportunity(book: MarketBook, kind: str) -> Opportunity:
    """Deterministic opportunities for end-to-end Paper Lab tests."""
    now = time.time()
    if kind == "cancel":
        # Fresh enough for consensus, old enough for Final Commit to CANCEL.
        aged = now - 3.2
        book.update(make_quote("coinbase", "BTC-USD", 97000, 97010, size=8, ts=aged))
        book.update(make_quote("kraken", "XBTUSD", 97320, 97340, size=6, ts=aged))
        return Opportunity(
            kind=OpportunityKind.CROSS_VENUE,
            edge_bps=32.0,
            net_edge_bps=28.0,
            notional=250,
            legs=[
                Leg("buy", "coinbase", "BTC-USD", 97010, True, 8),
                Leg("sell", "kraken", "XBTUSD", 97320, True, 6),
            ],
            summary="Buy BTC-USD on coinbase / sell XBTUSD on kraken",
            executable=True,
            ts=now,
            id=f"force-cancel-{int(now * 1000)}",
            pair="BTC/USDC",
            liquidity_usd=40000,
            execution_confidence=0.91,
        )
    seed_quality_book(book)
    cheap = book.get("coinbase", "BTC-USD")
    rich = book.get("kraken", "XBTUSD")
    assert cheap and rich
    suffix = kind
    return Opportunity(
        kind=OpportunityKind.CROSS_VENUE,
        edge_bps=32.0,
        net_edge_bps=28.0,
        notional=250,
        legs=[
            Leg("buy", "coinbase", "BTC-USD", cheap.ask, True, cheap.ask_size),
            Leg("sell", "kraken", "XBTUSD", rich.bid, True, rich.bid_size),
        ],
        summary="Buy BTC-USD on coinbase @ 97010 / sell XBTUSD on kraken @ 97320",
        executable=True,
        ts=now,
        id=f"force-{suffix}-{int(now * 1000)}",
        pair="BTC/USDC",
        liquidity_usd=40000,
        execution_confidence=0.4 if kind == "research" else 0.91,
    )
