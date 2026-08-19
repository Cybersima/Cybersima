from __future__ import annotations

from securetrade.engine.book import MarketBook
from securetrade.engine.forced import make_forced_opportunity, make_quote, seed_quality_book

__all__ = ["MarketBook", "make_forced_opportunity", "make_quote", "seed_quality_book", "seeded_book"]


def seeded_book() -> MarketBook:
    book = MarketBook()
    book.update(make_quote("binance", "BTCUSDT", 100000, 100010))
    book.update(make_quote("binance", "ETHUSDT", 2000, 2001))
    book.update(make_quote("binance", "ETHBTC", 0.0190, 0.0191))
    return book
