from __future__ import annotations

import time
from threading import RLock

from pulsearb.models import Quote
from pulsearb.symbols import normalize_asset, split_pair


class MarketBook:
    """Thread/async-safe last-quote book keyed by (venue, native_symbol)."""

    def __init__(self) -> None:
        self._quotes: dict[tuple[str, str], Quote] = {}
        self._lock = RLock()

    def update(self, quote: Quote) -> None:
        if quote.bid <= 0 or quote.ask <= 0 or quote.ask < quote.bid:
            return
        with self._lock:
            self._quotes[(quote.venue, quote.native_symbol)] = quote

    def get(self, venue: str, symbol: str) -> Quote | None:
        with self._lock:
            found = self._quotes.get((venue, symbol))
            if found:
                return found
            return self._quotes.get((venue, symbol.upper())) or self._quotes.get((venue, symbol.lower()))

    def snapshot(self) -> list[Quote]:
        with self._lock:
            return list(self._quotes.values())

    def by_canonical(self, canonical: str) -> list[Quote]:
        target = canonical.upper()
        with self._lock:
            return [q for q in self._quotes.values() if q.canonical.upper() == target]

    def find_pair(self, base: str, quote: str, venue: str | None = None) -> Quote | None:
        base_n = normalize_asset(base)
        quote_n = normalize_asset(quote)
        with self._lock:
            for item in self._quotes.values():
                if venue and item.venue != venue:
                    continue
                try:
                    left, right = split_pair(item.canonical)
                except ValueError:
                    continue
                if left == base_n and right == quote_n:
                    return item
        return None

    def binance_pair(self, base: str, quote: str) -> Quote | None:
        return self.find_pair(base, quote) or self.find_pair(base, quote, venue="simulator")

    def live_count(self, max_age: float) -> int:
        now = time.time()
        with self._lock:
            return sum(1 for q in self._quotes.values() if now - q.ts <= max_age)

    def size(self) -> int:
        with self._lock:
            return len(self._quotes)

    def convert(self, src: str, dst: str, amount: float, venue: str | None = None) -> float | None:
        src, dst = normalize_asset(src), normalize_asset(dst)
        if src == dst:
            return amount
        return self._leg(src, dst, amount, venue)

    def _leg(self, src: str, dst: str, amount: float, venue: str | None) -> float | None:
        quote = self.find_pair(src, dst, venue=venue)
        if quote:
            return amount * quote.bid
        quote = self.find_pair(dst, src, venue=venue)
        if quote and quote.ask > 0:
            return amount / quote.ask
        return None

    def pair_assets(self, native_symbol: str) -> tuple[str, str] | None:
        try:
            return split_pair(native_symbol)
        except ValueError:
            return None
