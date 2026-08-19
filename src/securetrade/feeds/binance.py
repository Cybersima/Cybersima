from __future__ import annotations

import asyncio
import json
import time

import httpx
import websockets

from securetrade.engine.book import MarketBook
from securetrade.feeds.base import Feed
from securetrade.models import Quote
from securetrade.symbols import canonical_from_binance


class BinanceFeed(Feed):
    name = "binance"

    def __init__(
        self,
        symbols: list[str],
        rest_url: str,
        ws_url: str,
        rest_poll_seconds: float = 1.0,
    ) -> None:
        self.symbols = [s.upper() for s in symbols]
        self.wanted = set(self.symbols)
        self.rest_url = rest_url.rstrip("/")
        self.ws_url = ws_url.rstrip("/")
        self.rest_poll_seconds = rest_poll_seconds

    async def run(self, book: MarketBook, status: dict[str, str]) -> None:
        status[self.name] = "starting"
        while True:
            try:
                await asyncio.gather(
                    self._ws_loop(book, status),
                    self._rest_loop(book, status),
                )
            except asyncio.CancelledError:
                status[self.name] = "stopped"
                raise
            except Exception as exc:
                status[self.name] = f"reconnect: {exc}"[:80]
                await asyncio.sleep(2.0)

    async def _rest_loop(self, book: MarketBook, status: dict[str, str]) -> None:
        async with httpx.AsyncClient(timeout=8.0) as client:
            while True:
                try:
                    response = await client.get(f"{self.rest_url}/api/v3/ticker/bookTicker")
                    response.raise_for_status()
                    rows = response.json()
                    now = time.time()
                    applied = 0
                    for row in rows:
                        symbol = str(row.get("symbol", "")).upper()
                        if symbol not in self.wanted:
                            continue
                        book.update(
                            Quote(
                                venue="binance",
                                native_symbol=symbol,
                                canonical=canonical_from_binance(symbol),
                                bid=float(row["bidPrice"]),
                                ask=float(row["askPrice"]),
                                ts=now,
                                asset_class="crypto",
                                executable=True,
                            )
                        )
                        applied += 1
                    status[self.name] = f"live rest ({applied})"
                except Exception as exc:
                    status[self.name] = f"rest error: {exc}"[:80]
                await asyncio.sleep(self.rest_poll_seconds)

    async def _ws_loop(self, book: MarketBook, status: dict[str, str]) -> None:
        streams = "/".join(f"{s.lower()}@bookTicker" for s in self.symbols)
        url = f"{self.ws_url}/stream?streams={streams}"
        async for websocket in websockets.connect(url, ping_interval=20, ping_timeout=20):
            status[self.name] = "ws connected"
            try:
                async for raw in websocket:
                    payload = json.loads(raw)
                    data = payload.get("data") or payload
                    symbol = str(data.get("s", "")).upper()
                    if symbol not in self.wanted:
                        continue
                    book.update(
                        Quote(
                            venue="binance",
                            native_symbol=symbol,
                            canonical=canonical_from_binance(symbol),
                            bid=float(data["b"]),
                            ask=float(data["a"]),
                            ts=time.time(),
                            asset_class="crypto",
                            executable=True,
                        )
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(1.5)
                continue
