from __future__ import annotations

import asyncio
import random
import time

from securetrade.engine.book import MarketBook
from securetrade.feeds.base import Feed
from securetrade.models import Quote
from securetrade.symbols import canonical_from_pair, to_native_symbol


SEED: dict[str, float] = {
    "BTC-USD": 97500.0,
    "ETH-USD": 3520.0,
    "SOL-USD": 178.0,
    "XRP-USD": 2.42,
    "ADA-USD": 0.78,
    "DOGE-USD": 0.32,
    "AVAX-USD": 38.5,
    "DOT-USD": 7.4,
    "LINK-USD": 18.2,
    "ATOM-USD": 6.1,
    "LTC-USD": 92.0,
    "NEAR-USD": 5.4,
    "APT-USD": 9.8,
    "ARB-USD": 0.82,
    "OP-USD": 1.72,
    "SUI-USD": 3.35,
    "FIL-USD": 5.1,
    "INJ-USD": 22.4,
    "AAVE-USD": 310.0,
    "UNI-USD": 9.4,
    "LDO-USD": 1.55,
    "BCH-USD": 430.0,
    "ETC-USD": 26.5,
    "XLM-USD": 0.39,
    "ALGO-USD": 0.31,
    "HBAR-USD": 0.27,
    "SHIB-USD": 0.000018,
    "PEPE-USD": 0.000011,
    "POL-USD": 0.48,
    "WIF-USD": 1.85,
    "RENDER-USD": 7.2,
    "SEI-USD": 0.41,
    "TIA-USD": 6.4,
    "ONDO-USD": 1.12,
    "ETH-BTC": 3520.0 / 97500.0,
    "LTC-BTC": 92.0 / 97500.0,
    "BTC-EUR": 89800.0,
    "ETH-EUR": 3240.0,
    "EUR-USD": 1.085,
    "GBP-USD": 1.275,
    "USD-JPY": 149.2,
    "AUD-USD": 0.662,
    "USD-CAD": 1.385,
    "USD-CHF": 0.868,
    "NZD-USD": 0.598,
    "EUR-GBP": 0.851,
    "EUR-JPY": 161.9,
    "GBP-JPY": 190.2,
    "EUR-CHF": 0.942,
    "AUD-JPY": 98.8,
    "EUR-AUD": 1.639,
    "EUR-CAD": 1.503,
    "GBP-AUD": 1.926,
    "GBP-CHF": 1.107,
    "AUD-NZD": 1.107,
    "NZD-JPY": 89.3,
    "CAD-JPY": 107.7,
    "CHF-JPY": 171.8,
    "EUR-NZD": 1.814,
    "GBP-CAD": 1.766,
    "AUD-CAD": 0.917,
    "USD-CNH": 7.24,
    "USD-SEK": 10.55,
    "USD-NOK": 10.72,
    "USD-MXN": 18.45,
    "USD-ZAR": 18.21,
    "USD-TRY": 32.45,
    "EUR-SEK": 11.45,
    "XAU-USD": 2685.0,
    "XAG-USD": 31.4,
    "WTI-USD": 78.2,
}

VENUE_BIAS = {
    "coinbase": 1.0,
    "kraken": 1.00015,
    "gemini": 0.99985,
    "bitstamp": 1.00025,
    "binance": 0.9997,
    "yahoo": 1.0004,
}


class SimulatorFeed(Feed):
    name = "simulator"

    def __init__(
        self,
        instruments: list[tuple[str, str, bool]],
        inject_gaps: bool = True,
        gap_every_seconds: float = 18.0,
    ) -> None:
        # (venue, canonical, executable)
        self.instruments = instruments
        self.inject_gaps = inject_gaps
        self.gap_every_seconds = gap_every_seconds
        self._mids: dict[str, float] = {}
        self._drift: dict[str, float] = {}
        for _venue, canon, _ok in instruments:
            self._mids[canon] = SEED.get(canon, 1.0)
            self._drift[canon] = 0.00005 if hash(canon) % 2 == 0 else -0.00005

    async def run(self, book: MarketBook, status: dict[str, str]) -> None:
        status[self.name] = "live"
        last_gap = time.time()
        while True:
            now = time.time()
            inject = self.inject_gaps and (now - last_gap) >= self.gap_every_seconds
            if inject:
                last_gap = now
            self._tick(book, inject=inject)
            status[self.name] = "gap injected" if inject else "live"
            await asyncio.sleep(0.25)

    def _tick(self, book: MarketBook, inject: bool) -> None:
        now = time.time()
        shock_canon = random.choice([c for _v, c, _e in self.instruments]) if inject else None
        shock_venue = random.choice(["coinbase", "kraken", "gemini", "bitstamp"]) if inject else None
        for venue, canon, executable in self.instruments:
            mid = self._walk(canon) * VENUE_BIAS.get(venue, 1.0)
            if inject and canon == shock_canon and venue == shock_venue:
                mid *= 0.988 if random.random() < 0.5 else 1.012
            spread = mid * (0.0002 if venue == "yahoo" else 0.00012)
            native = canon if venue == "yahoo" else to_native_symbol(venue, canon)
            try:
                canonical_from_pair(canon)
            except ValueError:
                continue
            book.update(
                Quote(
                    venue=venue if venue != "simulator" else "coinbase",
                    native_symbol=native,
                    canonical=canon,
                    bid=mid - spread / 2,
                    ask=mid + spread / 2,
                    ts=now,
                    asset_class=_asset_class(canon, venue),
                    executable=executable,
                )
            )

    def _walk(self, key: str) -> float:
        mid = self._mids.get(key, 1.0)
        drift = self._drift.get(key, 0.0)
        if random.random() < 0.01:
            self._drift[key] = -drift if drift else 0.00005
        shock = random.gauss(drift, 0.00022)
        mid = max(mid * (1 + shock), 1e-12)
        self._mids[key] = mid
        return mid


def _asset_class(canonical: str, venue: str) -> str:
    base = canonical.split("-")[0]
    if base in {"XAU", "XAG"}:
        return "metal"
    if base == "WTI":
        return "energy"
    if venue == "yahoo" and base not in {"BTC", "ETH", "SOL", "XRP"}:
        return "fx"
    return "crypto"
