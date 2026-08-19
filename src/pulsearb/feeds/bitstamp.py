from __future__ import annotations

import asyncio
import time

import httpx

from pulsearb.engine.book import MarketBook
from pulsearb.feeds.base import Feed
from pulsearb.feeds.headers import HTTP_HEADERS
from pulsearb.models import Quote
from pulsearb.symbols import canonical_from_pair, to_native_symbol


class BitstampFeed(Feed):
    name = "bitstamp"

    def __init__(self, symbols: list[str], rest_url: str, poll_seconds: float = 1.0) -> None:
        self.canonicals = [canonical_from_pair(s) for s in symbols]
        self.rest_url = rest_url.rstrip("/")
        self.poll_seconds = max(0.5, poll_seconds)

    async def run(self, book: MarketBook, status: dict[str, str]) -> None:
        status[self.name] = "starting"
        async with httpx.AsyncClient(timeout=8.0, headers=HTTP_HEADERS) as client:
            while True:
                try:
                    applied = 0
                    now = time.time()
                    for canon in self.canonicals:
                        native = to_native_symbol("bitstamp", canon)
                        response = await client.get(f"{self.rest_url}/api/v2/ticker/{native}/")
                        if response.status_code != 200:
                            continue
                        row = response.json()
                        bid = float(row.get("bid") or 0)
                        ask = float(row.get("ask") or 0)
                        if not bid or not ask:
                            continue
                        book.update(
                            Quote(
                                venue="bitstamp",
                                native_symbol=native,
                                canonical=canon,
                                bid=bid,
                                ask=ask,
                                ts=now,
                                asset_class="crypto",
                                executable=True,
                            )
                        )
                        applied += 1
                    status[self.name] = f"live ({applied})"
                except asyncio.CancelledError:
                    status[self.name] = "stopped"
                    raise
                except Exception as exc:
                    status[self.name] = f"error: {exc}"[:80]
                await asyncio.sleep(self.poll_seconds)
