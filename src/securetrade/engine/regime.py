from __future__ import annotations

import statistics
import time

from securetrade.engine.book import MarketBook
from securetrade.models import MarketRegime, Opportunity


class RegimeDetector:
    def __init__(self) -> None:
        self._mids: dict[str, list[float]] = {}

    def observe(self, book: MarketBook) -> None:
        for quote in book.snapshot():
            series = self._mids.setdefault(quote.canonical, [])
            series.append(quote.mid)
            if len(series) > 40:
                del series[0]

    def classify(self, opportunity: Opportunity, book: MarketBook) -> MarketRegime:
        self.observe(book)
        pair = opportunity.pair.replace("/", "-") if opportunity.pair else ""
        series = self._mids.get(pair) or []
        if opportunity.net_edge_bps > 700:
            return MarketRegime.ABNORMAL
        spreads = [q.spread_bps for q in book.snapshot() if not pair or q.canonical == pair]
        if spreads and statistics.median(spreads) > 40:
            return MarketRegime.ILLIQUID
        if len(series) >= 8:
            mean = statistics.mean(series)
            if mean:
                vol = statistics.pstdev(series) / mean * 10_000
                if vol > 40:
                    return MarketRegime.HIGHLY_VOLATILE
                drift = (series[-1] - series[0]) / mean * 10_000
                if abs(drift) > 25:
                    return MarketRegime.TRENDING
        _ = time.time()
        return MarketRegime.NORMAL
