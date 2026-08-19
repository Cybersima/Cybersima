from __future__ import annotations

import time

import httpx

from securetrade.engine.book import MarketBook
from securetrade.feeds.base import Feed
from securetrade.feeds.headers import HTTP_HEADERS
from securetrade.models import Quote
from securetrade.symbols import canonical_from_pair, normalize_asset, to_native_symbol


class KrakenFeed(Feed):
    name = "kraken"

    def __init__(self, symbols: list[str], rest_url: str, poll_seconds: float = 1.0) -> None:
        self.canonicals = [canonical_from_pair(s) for s in symbols]
        self.rest_url = rest_url.rstrip("/")
        self.poll_seconds = max(0.5, poll_seconds)
        self._key_to_canonical: dict[str, str] = {}

    async def run(self, book: MarketBook, status: dict[str, str]) -> None:
        status[self.name] = "starting"
        async with httpx.AsyncClient(timeout=10.0, headers=HTTP_HEADERS) as client:
            while True:
                try:
                    if not self._key_to_canonical:
                        await self._load_pairs(client)
                    applied = await self._poll(client, book)
                    status[self.name] = f"live ({applied})"
                except Exception as exc:
                    status[self.name] = f"error: {exc}"[:80]
                await self.sleep_or_stop(self.poll_seconds)

    async def _load_pairs(self, client: httpx.AsyncClient) -> None:
        wanted = {item.upper() for item in self.canonicals}
        response = await client.get(f"{self.rest_url}/0/public/AssetPairs")
        response.raise_for_status()
        payload = response.json()
        mapping: dict[str, str] = {}
        for key, meta in (payload.get("result") or {}).items():
            wsname = str(meta.get("wsname") or "").replace("/", "-")
            alt = str(meta.get("altname") or "")
            candidates = [wsname, alt]
            for raw in candidates:
                if not raw:
                    continue
                try:
                    canon = canonical_from_pair(raw.replace("XBT", "BTC"))
                except ValueError:
                    continue
                if canon in wanted:
                    mapping[key] = canon
                    mapping[alt.upper()] = canon
        # Fallback from our own native names if AssetPairs is sparse.
        for canon in self.canonicals:
            mapping.setdefault(to_native_symbol("kraken", canon).upper(), canon)
        self._key_to_canonical = mapping

    async def _poll(self, client: httpx.AsyncClient, book: MarketBook) -> int:
        pairs = ",".join(to_native_symbol("kraken", item) for item in self.canonicals)
        response = await client.get(f"{self.rest_url}/0/public/Ticker", params={"pair": pairs})
        response.raise_for_status()
        payload = response.json()
        applied = 0
        now = time.time()
        for key, row in (payload.get("result") or {}).items():
            canon = self._key_to_canonical.get(key) or self._guess_canonical(key)
            if not canon:
                continue
            ask = float((row.get("a") or [0])[0] or 0)
            bid = float((row.get("b") or [0])[0] or 0)
            if not bid or not ask:
                continue
            book.update(
                Quote(
                    venue="kraken",
                    native_symbol=key,
                    canonical=canon,
                    bid=bid,
                    ask=ask,
                    ts=now,
                    asset_class="crypto",
                    executable=True,
                )
            )
            applied += 1
        return applied

    def _guess_canonical(self, key: str) -> str | None:
        try:
            return canonical_from_pair(key.replace("XBT", "BTC"))
        except ValueError:
            cleaned = key.upper()
            for prefix in ("XXBT", "XETH", "XLTC", "XXRP", "XXLM"):
                cleaned = cleaned.replace(prefix, normalize_asset(prefix))
            for prefix in ("ZUSD", "ZEUR"):
                cleaned = cleaned.replace(prefix, normalize_asset(prefix))
            try:
                return canonical_from_pair(cleaned)
            except ValueError:
                return None
