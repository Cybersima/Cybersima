from __future__ import annotations

import asyncio
import time
from typing import Any

from securetrade.engine.book import MarketBook
from securetrade.feeds.base import Feed
from securetrade.models import Quote


class YahooFeed(Feed):
    """Polls Yahoo Finance. This is delayed retail data, not a 1ms venue."""

    name = "yahoo"

    def __init__(self, symbols: list[dict[str, str]], poll_seconds: float = 2.0) -> None:
        self.symbols = symbols
        self.poll_seconds = max(1.0, poll_seconds)

    async def run(self, book: MarketBook, status: dict[str, str]) -> None:
        status[self.name] = "starting"
        while True:
            try:
                applied = await asyncio.to_thread(self._poll_once, book)
                status[self.name] = f"live ({applied})"
            except asyncio.CancelledError:
                status[self.name] = "stopped"
                raise
            except Exception as exc:
                status[self.name] = f"error: {exc}"[:80]
            await asyncio.sleep(self.poll_seconds)

    def _poll_once(self, book: MarketBook) -> int:
        import yfinance as yf

        tickers = [row["ticker"] for row in self.symbols]
        batch = yf.Tickers(" ".join(tickers))
        applied = 0
        now = time.time()
        for row in self.symbols:
            ticker = row["ticker"]
            info = self._fast_info(batch.tickers.get(ticker))
            bid, ask = self._bid_ask(info)
            if bid <= 0 or ask <= 0:
                continue
            book.update(
                Quote(
                    venue="yahoo",
                    native_symbol=row["canonical"],
                    canonical=row["canonical"],
                    bid=bid,
                    ask=ask,
                    ts=now,
                    asset_class=row.get("asset_class", "fx"),
                    executable=False,
                )
            )
            applied += 1
        return applied

    def _fast_info(self, ticker: Any) -> dict[str, Any]:
        if ticker is None:
            return {}
        try:
            info = ticker.fast_info
            if hasattr(info, "items"):
                return dict(info)
            return dict(info) if info else {}
        except Exception:
            return {}

    def _bid_ask(self, info: dict[str, Any]) -> tuple[float, float]:
        last = _num(info.get("lastPrice") or info.get("last_price") or info.get("regularMarketPrice"))
        bid = _num(info.get("bid") or info.get("bidPrice"))
        ask = _num(info.get("ask") or info.get("askPrice"))
        if bid > 0 and ask > 0:
            return bid, ask
        if last > 0:
            width = last * 0.00015
            return last - width, last + width
        return 0.0, 0.0


def _num(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0
