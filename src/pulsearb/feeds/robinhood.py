from __future__ import annotations

import time

import httpx

from pulsearb.engine.book import MarketBook
from pulsearb.engine.robinhood_auth import robinhood_headers
from pulsearb.feeds.base import Feed
from pulsearb.feeds.headers import HTTP_HEADERS
from pulsearb.models import Quote
from pulsearb.symbols import canonical_from_pair, to_native_symbol

BASE_URL = "https://trading.robinhood.com"


class RobinhoodFeed(Feed):
    """Polls Robinhood's v2 best_bid_ask endpoint. Like Coinbase and OANDA,
    every Robinhood Crypto API call requires a signed request, market data
    included - there is no public/no-auth ticker the way Kraken has."""

    name = "robinhood"

    def __init__(
        self,
        symbols: list[str],
        api_key: str,
        private_key_base64: str,
        poll_seconds: float = 1.0,
    ) -> None:
        self.canonicals = [canonical_from_pair(s) for s in symbols]
        self.api_key = api_key
        self.private_key_base64 = private_key_base64
        self.poll_seconds = max(0.5, poll_seconds)
        self._native_to_canonical = {
            to_native_symbol("robinhood", canon): canon for canon in self.canonicals
        }

    async def run(self, book: MarketBook, status: dict[str, str]) -> None:
        status[self.name] = "starting"
        async with httpx.AsyncClient(timeout=10.0, headers=HTTP_HEADERS) as client:
            while True:
                try:
                    applied = await self._poll(client, book)
                    status[self.name] = f"live ({applied})"
                except Exception as exc:
                    status[self.name] = f"error: {exc}"[:80]
                await self.sleep_or_stop(self.poll_seconds)

    async def _poll(self, client: httpx.AsyncClient, book: MarketBook) -> int:
        symbols = list(self._native_to_canonical.keys())
        query = "&".join(f"symbol={s}" for s in symbols)
        path = f"/api/v2/crypto/marketdata/best_bid_ask/?{query}"
        headers = robinhood_headers(self.api_key, self.private_key_base64, "GET", path, "")
        response = await client.get(f"{BASE_URL}{path}", headers=headers)
        if response.status_code == 401:
            raise RuntimeError("Robinhood rejected the signed request (401) - check keys\\robinhood.json")
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("results") if isinstance(payload, dict) else payload
        now = time.time()
        applied = 0
        for row in rows or []:
            native = str(row.get("symbol") or "")
            canonical = self._native_to_canonical.get(native)
            if not canonical:
                continue
            try:
                # Field names here are a best-effort guess, NOT confirmed
                # against a real response - Robinhood's reference script
                # never parses this endpoint's output, only prints it raw.
                # Tries a few plausible candidates in order; if none match,
                # the symbol is just skipped this poll cycle (safe default:
                # no stale/wrong price, just no price yet) rather than
                # silently trusting a guessed field that might be wrong.
                bid = float(row.get("bid_inclusive_of_sell_spread") or row.get("bid_price") or row.get("bid") or 0)
                ask = float(row.get("ask_inclusive_of_buy_spread") or row.get("ask_price") or row.get("ask") or 0)
            except (TypeError, ValueError):
                continue
            if bid <= 0 or ask <= 0:
                continue
            book.update(
                Quote(
                    venue=self.name, native_symbol=native, canonical=canonical,
                    bid=bid, ask=ask, ts=now, asset_class="crypto", executable=True,
                )
            )
            applied += 1
        return applied
