from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

from securetrade.engine.book import MarketBook


class Feed(ABC):
    name: str = "feed"

    @abstractmethod
    async def run(self, book: MarketBook, status: dict[str, str]) -> None:
        raise NotImplementedError

    async def sleep_or_stop(self, seconds: float) -> None:
        await asyncio.sleep(seconds)
