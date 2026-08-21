from __future__ import annotations

import time

from pulsearb.engine.book import MarketBook
from pulsearb.models import Quote
from pulsearb.symbols import canonical_from_binance


def make_quote(venue: str, symbol: str, bid: float, ask: float, executable: bool = True) -> Quote:
    canonical = symbol if "-" in symbol else canonical_from_binance(symbol)
    return Quote(
        venue=venue,
        native_symbol=symbol,
        canonical=canonical,
        bid=bid,
        ask=ask,
        ts=time.time(),
        executable=executable,
    )


def seeded_book() -> MarketBook:
    book = MarketBook()
    book.update(make_quote("binance", "BTCUSDT", 100000, 100010))
    book.update(make_quote("binance", "ETHUSDT", 2000, 2001))
    book.update(make_quote("binance", "ETHBTC", 0.01950, 0.01951))
    return book
