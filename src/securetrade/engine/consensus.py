from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field

from securetrade.engine.book import MarketBook
from securetrade.models import Opportunity, Quote
from securetrade.symbols import comparison_key


VENUE_RELIABILITY = {
    "coinbase": 0.96,
    "kraken": 0.94,
    "gemini": 0.93,
    "bitstamp": 0.90,
    "binance": 0.92,
    "simulator": 0.88,
    "yahoo": 0.70,
}


@dataclass
class ConsensusResult:
    ok: bool
    sources: int
    median_mid: float
    outlier_venues: list[str]
    stale_venues: list[str]
    quarantined: list[str]
    latency_ms: float
    timestamps: dict[str, float]
    notes: list[str]

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "sources": self.sources,
            "median_mid": self.median_mid,
            "outlier_venues": self.outlier_venues,
            "stale_venues": self.stale_venues,
            "quarantined": self.quarantined,
            "latency_ms": self.latency_ms,
            "timestamps": self.timestamps,
            "notes": self.notes,
        }


class PriceConsensus:
    """No single exchange determines truth."""

    def __init__(self, stale_seconds: float = 8.0, outlier_bps: float = 80.0) -> None:
        self.stale_seconds = stale_seconds
        self.outlier_bps = outlier_bps
        self.quarantine: dict[str, float] = {}
        self.quarantine_seconds = 30.0

    def evaluate(self, opportunity: Opportunity, book: MarketBook, now: float | None = None) -> ConsensusResult:
        now = now or time.time()
        pair = opportunity.pair or (opportunity.legs[0].symbol if opportunity.legs else "")
        quotes = self._related_quotes(book, opportunity)
        timestamps = {q.venue: q.ts for q in quotes}
        stale = [q.venue for q in quotes if now - q.ts > self.stale_seconds]
        live = [q for q in quotes if q.venue not in stale]
        mids = [q.mid for q in live if q.mid > 0]
        median = statistics.median(mids) if mids else 0.0
        outliers: list[str] = []
        if median > 0:
            for quote in live:
                deviation = abs(quote.mid - median) / median * 10_000
                if deviation >= self.outlier_bps:
                    outliers.append(quote.venue)
                    self.quarantine[quote.venue] = now + self.quarantine_seconds
        quarantined = [venue for venue, until in self.quarantine.items() if until > now]
        latency = max((q.latency_ms for q in quotes), default=0.0)
        if not latency and quotes:
            latency = max((now - q.ts) * 1000 for q in quotes)
        notes = []
        if len(live) >= 2:
            notes.append("Multiple markets confirmed price")
        if stale:
            notes.append(f"Stale feeds ignored: {', '.join(stale)}")
        if outliers:
            notes.append(f"Outliers quarantined: {', '.join(outliers)}")
        ok = len(live) >= 1 and len(outliers) < max(1, len(live))
        if pair:
            _ = pair
        return ConsensusResult(
            ok=ok,
            sources=len(live),
            median_mid=median,
            outlier_venues=outliers,
            stale_venues=stale,
            quarantined=quarantined,
            latency_ms=round(latency, 2),
            timestamps=timestamps,
            notes=notes,
        )

    def _related_quotes(self, book: MarketBook, opportunity: Opportunity) -> list[Quote]:
        quotes: list[Quote] = []
        seen: set[tuple[str, str]] = set()
        for leg in opportunity.legs:
            quote = book.get(leg.venue, leg.symbol)
            if quote and (quote.venue, quote.native_symbol) not in seen:
                quotes.append(quote)
                seen.add((quote.venue, quote.native_symbol))
        if opportunity.pair:
            for quote in book.by_canonical(opportunity.pair.replace("/", "-")):
                key = (quote.venue, quote.native_symbol)
                if key not in seen:
                    quotes.append(quote)
                    seen.add(key)
        if len(quotes) < 2:
            usd = {"USD", "USDT", "USDC"}
            keys = {comparison_key(q.canonical, usd) for q in quotes if q.canonical}
            for quote in book.snapshot():
                if comparison_key(quote.canonical, usd) in keys:
                    key = (quote.venue, quote.native_symbol)
                    if key not in seen:
                        quotes.append(quote)
                        seen.add(key)
        return quotes
