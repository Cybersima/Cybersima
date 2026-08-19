from __future__ import annotations

import asyncio
import random
import time

from pulsearb.engine.book import MarketBook
from pulsearb.feeds.base import Feed
from pulsearb.models import Quote
from pulsearb.symbols import canonical_from_binance, split_binance_symbol


SEED_PRICES: dict[str, float] = {
    "BTCUSDT": 97500.0,
    "ETHUSDT": 3520.0,
    "BNBUSDT": 605.0,
    "SOLUSDT": 178.0,
    "XRPUSDT": 2.42,
    "ADAUSDT": 0.78,
    "DOGEUSDT": 0.32,
    "AVAXUSDT": 38.5,
    "DOTUSDT": 7.4,
    "LINKUSDT": 18.2,
    "ATOMUSDT": 6.1,
    "LTCUSDT": 92.0,
    "NEARUSDT": 5.4,
    "APTUSDT": 9.8,
    "ARBUSDT": 0.82,
    "OPUSDT": 1.72,
    "SUIUSDT": 3.35,
    "TONUSDT": 5.55,
    "TRXUSDT": 0.24,
    "FILUSDT": 5.1,
    "INJUSDT": 22.4,
    "AAVEUSDT": 310.0,
    "UNIUSDT": 9.4,
    "LDOUSDT": 1.55,
    "RENDERUSDT": 7.2,
    "WIFUSDT": 1.85,
    "PEPEUSDT": 0.000011,
    "SHIBUSDT": 0.000018,
    "BCHUSDT": 430.0,
    "ETCUSDT": 26.5,
    "XLMUSDT": 0.39,
    "ALGOUSDT": 0.31,
    "HBARUSDT": 0.27,
    "SANDUSDT": 0.44,
    "GRTUSDT": 0.21,
    "STXUSDT": 1.72,
    "IMXUSDT": 1.18,
    "RUNEUSDT": 5.4,
    "POLUSDT": 0.48,
    "WLDUSDT": 2.15,
    "SEIUSDT": 0.41,
    "TIAUSDT": 6.4,
    "JUPUSDT": 0.82,
    "PENDLEUSDT": 4.1,
    "ENAUSDT": 0.62,
    "ONDOUSDT": 1.12,
    "EURUSDT": 1.085,
    "USDCUSDT": 1.0001,
    "FDUSDUSDT": 0.9998,
    "ETHEUR": 3240.0,
    "BTCEUR": 89800.0,
}


class SimulatorFeed(Feed):
    name = "simulator"

    def __init__(
        self,
        binance_symbols: list[str],
        yahoo_symbols: list[dict[str, str]],
        inject_gaps: bool = True,
        gap_every_seconds: float = 18.0,
    ) -> None:
        self.binance_symbols = [s.upper() for s in binance_symbols]
        self.yahoo_symbols = yahoo_symbols
        self.inject_gaps = inject_gaps
        self.gap_every_seconds = gap_every_seconds
        self._mids: dict[str, float] = {}
        self._bootstrap()

    def _bootstrap(self) -> None:
        for symbol in self.binance_symbols:
            if symbol in SEED_PRICES:
                self._mids[symbol] = SEED_PRICES[symbol]
                continue
            try:
                base, quote = split_binance_symbol(symbol)
            except ValueError:
                self._mids[symbol] = 1.0
                continue
            base_usdt = SEED_PRICES.get(f"{base}USDT")
            quote_usdt = SEED_PRICES.get(f"{quote}USDT")
            if base_usdt and quote_usdt:
                self._mids[symbol] = base_usdt / quote_usdt
            elif base_usdt and quote == "EUR":
                self._mids[symbol] = base_usdt / SEED_PRICES["EURUSDT"]
            else:
                self._mids[symbol] = 1.0
        fx = {
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
            "USD-CNH": 7.24,
            "USD-SEK": 10.55,
            "USD-NOK": 10.72,
            "USD-MXN": 18.45,
            "BTC-USD": SEED_PRICES["BTCUSDT"] * 1.0004,
            "ETH-USD": SEED_PRICES["ETHUSDT"] * 1.0003,
            "SOL-USD": SEED_PRICES["SOLUSDT"] * 0.9997,
            "XRP-USD": SEED_PRICES["XRPUSDT"] * 1.0002,
            "BNB-USD": SEED_PRICES["BNBUSDT"] * 1.0001,
            "XAU-USD": 2685.0,
            "XAG-USD": 31.4,
            "WTI-USD": 78.2,
        }
        for row in self.yahoo_symbols:
            canonical = row["canonical"]
            self._mids[canonical] = fx.get(canonical, 1.0)

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
        gap_symbol = random.choice(self.binance_symbols) if inject else None
        for symbol in self.binance_symbols:
            mid = self._walk(symbol)
            if symbol == gap_symbol:
                mid *= 0.994 if random.random() < 0.5 else 1.006
            spread = mid * 0.00012
            book.update(
                Quote(
                    venue="simulator",
                    native_symbol=symbol,
                    canonical=canonical_from_binance(symbol),
                    bid=mid - spread / 2,
                    ask=mid + spread / 2,
                    ts=now,
                    asset_class="crypto",
                    executable=True,
                )
            )
        for row in self.yahoo_symbols:
            canonical = row["canonical"]
            mid = self._walk(canonical)
            if inject and canonical.endswith("-USD") and random.random() < 0.4:
                mid *= 1.004
            spread = mid * 0.0002
            book.update(
                Quote(
                    venue="yahoo",
                    native_symbol=canonical,
                    canonical=canonical,
                    bid=mid - spread / 2,
                    ask=mid + spread / 2,
                    ts=now,
                    asset_class=row.get("asset_class", "fx"),
                    executable=False,
                )
            )

    def _walk(self, key: str) -> float:
        mid = self._mids.get(key, 1.0)
        shock = random.gauss(0, 0.00025)
        mid = max(mid * (1 + shock), 1e-12)
        self._mids[key] = mid
        return mid
