from __future__ import annotations

import asyncio
import json
import time

import httpx
import websockets

from pulsearb.engine.book import MarketBook
from pulsearb.feeds.base import Feed
from pulsearb.feeds.headers import HTTP_HEADERS
from pulsearb.models import Quote
from pulsearb.symbols import canonical_from_pair, pair_asset_class


class CoinbaseFeed(Feed):
    name = "coinbase"

    def __init__(self, symbols: list[str], rest_url: str, ws_url: str, poll_seconds: float = 1.0) -> None:
        self.symbols = [s.upper() for s in symbols]
        self.rest_url = rest_url.rstrip("/")
        self.ws_url = ws_url
        self.poll_seconds = max(0.5, poll_seconds)

    async def run(self, book: MarketBook, status: dict[str, str]) -> None:
        status[self.name] = "starting"
        while True:
            try:
                await asyncio.gather(self._ws_loop(book, status), self._rest_loop(book, status))
            except asyncio.CancelledError:
                status[self.name] = "stopped"
                raise
            except Exception as exc:
                status[self.name] = f"reconnect: {exc}"[:80]
                await asyncio.sleep(2.0)

    def _quote(self, product_id: str, bid: float, ask: float, ts: float | None = None) -> Quote:
        return Quote(
            venue="coinbase",
            native_symbol=product_id,
            canonical=canonical_from_pair(product_id),
            bid=bid,
            ask=ask,
            ts=time.time() if ts is None else ts,
            asset_class=pair_asset_class(product_id),
            executable=True,
        )

    async def _rest_loop(self, book: MarketBook, status: dict[str, str]) -> None:
        sem = asyncio.Semaphore(8)

        async def one(client: httpx.AsyncClient, product: str, ts: float) -> bool:
            async with sem:
                response = await client.get(f"{self.rest_url}/products/{product}/ticker")
            if response.status_code != 200:
                return False
            row = response.json()
            bid = float(row.get("bid") or 0)
            ask = float(row.get("ask") or 0)
            if not bid or not ask:
                return False
            book.update(self._quote(product, bid, ask, ts=ts))
            return True

        async with httpx.AsyncClient(timeout=8.0, headers=HTTP_HEADERS) as client:
            while True:
                try:
                    now = time.time()
                    results = await asyncio.gather(
                        *(one(client, product, now) for product in self.symbols),
                        return_exceptions=True,
                    )
                    applied = sum(1 for item in results if item is True)
                    status[self.name] = f"live rest ({applied})"
                except Exception as exc:
                    status[self.name] = f"rest error: {exc}"[:80]
                await asyncio.sleep(self.poll_seconds)

    async def _ws_loop(self, book: MarketBook, status: dict[str, str]) -> None:
        async for websocket in websockets.connect(
            self.ws_url, ping_interval=20, ping_timeout=20, additional_headers=HTTP_HEADERS
        ):
            await websocket.send(
                json.dumps(
                    {
                        "type": "subscribe",
                        "product_ids": self.symbols,
                        "channels": ["ticker"],
                    }
                )
            )
            status[self.name] = "ws connected"
            try:
                async for raw in websocket:
                    payload = json.loads(raw)
                    if payload.get("type") != "ticker":
                        continue
                    product = str(payload.get("product_id", "")).upper()
                    if product not in self.symbols:
                        continue
                    bid = float(payload.get("best_bid") or 0)
                    ask = float(payload.get("best_ask") or 0)
                    if bid and ask:
                        book.update(self._quote(product, bid, ask))
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(1.5)
                continue
