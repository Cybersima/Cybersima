from __future__ import annotations

import time
from threading import RLock

from pulsearb.models import Quote
from pulsearb.symbols import split_binance_symbol


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
            return self._quotes.get((venue, symbol))

    def snapshot(self) -> list[Quote]:
        with self._lock:
            return list(self._quotes.values())

    def by_canonical(self, canonical: str) -> list[Quote]:
        target = canonical.upper()
        with self._lock:
            return [q for q in self._quotes.values() if q.canonical.upper() == target]

    def binance_pair(self, base: str, quote: str) -> Quote | None:
        native = f"{base}{quote}".upper()
        found = self.get("binance", native)
        if found:
            return found
        # Simulator uses the same native symbols.
        return self.get("simulator", native)

    def live_count(self, max_age: float) -> int:
        now = time.time()
        with self._lock:
            return sum(1 for q in self._quotes.values() if now - q.ts <= max_age)

    def size(self) -> int:
        with self._lock:
            return len(self._quotes)

    def convert(self, src: str, dst: str, amount: float) -> float | None:
        """Walk bid/ask from src asset to dst using Binance/simulator pairs."""
        src, dst = src.upper(), dst.upper()
        if src == dst:
            return amount
        direct = self._leg(src, dst, amount)
        if direct is not None:
            return direct
        return None

    def _leg(self, src: str, dst: str, amount: float) -> float | None:
        quote = self.binance_pair(src, dst)
        if quote:
            # Selling SRC (base) for DST (quote) hits the bid.
            return amount * quote.bid
        quote = self.binance_pair(dst, src)
        if quote:
            # Buying DST (base) with SRC (quote) hits the ask.
            if quote.ask <= 0:
                return None
            return amount / quote.ask
        return None

    def pair_assets(self, native_symbol: str) -> tuple[str, str] | None:
        try:
            return split_binance_symbol(native_symbol)
        except ValueError:
            return None
