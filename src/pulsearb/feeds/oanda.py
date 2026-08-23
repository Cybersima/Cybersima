from __future__ import annotations

import time

import httpx

from pulsearb.engine.book import MarketBook
from pulsearb.feeds.base import Feed
from pulsearb.feeds.headers import HTTP_HEADERS
from pulsearb.models import Quote
from pulsearb.symbols import canonical_from_pair, to_native_symbol

PRACTICE_URL = "https://api-fxpractice.oanda.com"
LIVE_URL = "https://api-fxtrade.oanda.com"


class OandaFeed(Feed):
    """Polls OANDA's v20 pricing endpoint. Unlike Kraken's public ticker,
    OANDA requires an authenticated account for every call, market data
    included - this feed simply won't produce quotes without a valid
    account_id + access_token, same as the app requiring Coinbase auth for
    its own market data in the other build this project is a sibling of.
    """

    name = "oanda"

    def __init__(
        self,
        symbols: list[str],
        account_id: str,
        access_token: str,
        environment: str = "practice",
        poll_seconds: float = 2.0,
    ) -> None:
        self.canonicals = [canonical_from_pair(s) for s in symbols]
        self.account_id = account_id
        self.access_token = access_token
        self.base_url = LIVE_URL if str(environment).strip().lower() == "live" else PRACTICE_URL
        self.poll_seconds = max(1.0, poll_seconds)
        self._instrument_to_canonical = {
            to_native_symbol("oanda", canon): canon for canon in self.canonicals
        }

    async def run(self, book: MarketBook, status: dict[str, str]) -> None:
        status[self.name] = "starting"
        headers = {**HTTP_HEADERS, "Authorization": f"Bearer {self.access_token}"}
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            while True:
                try:
                    applied = await self._poll(client, book)
                    status[self.name] = f"live ({applied})"
                except Exception as exc:
                    status[self.name] = f"error: {exc}"[:80]
                await self.sleep_or_stop(self.poll_seconds)

    async def _poll(self, client: httpx.AsyncClient, book: MarketBook) -> int:
        instruments = ",".join(self._instrument_to_canonical.keys())
        url = f"{self.base_url}/v3/accounts/{self.account_id}/pricing"
        response = await client.get(url, params={"instruments": instruments})
        if response.status_code == 401:
            raise RuntimeError("OANDA rejected the access token (401) - check keys/oanda.json")
        response.raise_for_status()
        payload = response.json()
        now = time.time()
        applied = 0
        for row in payload.get("prices") or []:
            instrument = str(row.get("instrument") or "")
            canonical = self._instrument_to_canonical.get(instrument)
            if not canonical:
                continue
            if str(row.get("status") or "tradeable") != "tradeable":
                continue
            bids = row.get("bids") or []
            asks = row.get("asks") or []
            if not bids or not asks:
                continue
            try:
                bid = float(bids[0].get("price"))
                ask = float(asks[0].get("price"))
            except (TypeError, ValueError):
                continue
            if bid <= 0 or ask <= 0:
                continue
            book.update(
                Quote(
                    venue=self.name,
                    native_symbol=instrument,
                    canonical=canonical,
                    bid=bid,
                    ask=ask,
                    ts=now,
                    asset_class="fx",
                    executable=True,
                )
            )
            applied += 1
        return applied
