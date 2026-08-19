from __future__ import annotations

import asyncio
import time
from collections import deque

from pulsearb.config import AppConfig
from pulsearb.engine.arbitrage import detect_cross_venue, detect_triangles, discover_triangles
from pulsearb.engine.book import MarketBook
from pulsearb.engine.broker import Broker, LiveBinanceBroker, PaperBroker
from pulsearb.engine.risk import RiskManager
from pulsearb.feeds.binance import BinanceFeed
from pulsearb.feeds.simulator import SimulatorFeed
from pulsearb.feeds.yahoo import YahooFeed
from pulsearb.models import EngineStats, Fill, Opportunity


class Engine:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.book = MarketBook()
        self.stats = EngineStats(started_at=time.time())
        self.opportunities: deque[Opportunity] = deque(maxlen=80)
        self.fills: deque[Fill] = deque(maxlen=80)
        self.seen: set[str] = set()
        self.listeners: set[asyncio.Queue] = set()
        self.risk = RiskManager(
            max_notional_usdt=float(config.risk.get("max_notional_usdt", 250)),
            max_open_orders=int(config.risk.get("max_open_orders", 4)),
            daily_loss_limit_usdt=float(config.risk.get("daily_loss_limit_usdt", 100)),
            cooldown_seconds=float(config.risk.get("cooldown_seconds", 8)),
        )
        self.paper = PaperBroker(self.risk)
        self.broker: Broker = self.paper
        if config.live_enabled():
            binance = config.markets.get("binance") or {}
            rest = binance.get("testnet_rest_url" if config.env.binance_testnet else "rest_url")
            self.broker = LiveBinanceBroker(
                risk=self.risk,
                api_key=config.env.binance_api_key,
                api_secret=config.env.binance_api_secret,
                rest_url=str(rest),
                paper_fallback=self.paper,
            )
        self.triangles = discover_triangles(config.binance_symbols)
        self._lock = asyncio.Lock()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=8)
        self.listeners.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self.listeners.discard(queue)

    def snapshot(self) -> dict:
        quotes = sorted(self.book.snapshot(), key=lambda q: (q.venue, q.native_symbol))
        return {
            "stats": {
                **self.stats.to_dict(),
                "paper_pnl": round(self.paper.pnl, 4),
                "killed": self.risk.killed,
                "execution": "live" if self.config.live_enabled() else "paper",
                "uptime_s": round(time.time() - self.stats.started_at, 1),
                "triangles": len(self.triangles),
            },
            "quotes": [q.to_dict() for q in quotes],
            "opportunities": [o.to_dict() for o in list(self.opportunities)[:40]],
            "fills": [f.to_dict() for f in list(self.fills)[:40]],
        }

    async def broadcast(self) -> None:
        data = self.snapshot()
        dead = []
        for queue in list(self.listeners):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(data)
            except asyncio.QueueFull:
                dead.append(queue)
        for queue in dead:
            self.unsubscribe(queue)

    async def run_feeds(self) -> None:
        tasks = []
        markets = self.config.markets
        settings = self.config.settings
        sim = settings.get("simulator") or {}
        binance_cfg = markets.get("binance") or {}
        yahoo_cfg = markets.get("yahoo") or {}

        demo_only = self.config.env.demo_only
        if sim.get("enabled", True) or demo_only:
            tasks.append(
                SimulatorFeed(
                    binance_symbols=self.config.binance_symbols,
                    yahoo_symbols=self.config.yahoo_symbols,
                    inject_gaps=bool(sim.get("inject_gaps", True)),
                    gap_every_seconds=float(sim.get("gap_every_seconds", 18)),
                ).run(self.book, self.stats.feed_status)
            )
        if binance_cfg.get("enabled", True) and not demo_only:
            rest = binance_cfg.get("testnet_rest_url" if self.config.env.binance_testnet else "rest_url")
            ws = binance_cfg.get("testnet_ws_url" if self.config.env.binance_testnet else "ws_url")
            tasks.append(
                BinanceFeed(
                    symbols=self.config.binance_symbols,
                    rest_url=str(rest),
                    ws_url=str(ws),
                    rest_poll_seconds=float(settings.get("binance_rest_poll_seconds", 1.0)),
                ).run(self.book, self.stats.feed_status)
            )
        if yahoo_cfg.get("enabled", True) and not demo_only:
            tasks.append(
                YahooFeed(
                    symbols=self.config.yahoo_symbols,
                    poll_seconds=float(yahoo_cfg.get("poll_seconds") or settings.get("yahoo_poll_seconds", 2.0)),
                ).run(self.book, self.stats.feed_status)
            )
        if not tasks:
            raise RuntimeError("No market feeds enabled")
        await asyncio.gather(*tasks)

    async def run_scanner(self) -> None:
        interval = self.config.scan_interval_ms / 1000.0
        fees = self.config.fees
        fee_map = {
            "binance": float(fees.get("binance_taker_bps", 10)),
            "simulator": float(fees.get("binance_taker_bps", 10)),
            "yahoo": float(fees.get("yahoo_taker_bps", 0)),
        }
        extra = float(fees.get("extra_slippage_bps", 2))
        min_alert = float(self.config.settings.get("min_edge_bps", 8))
        min_exec = float(self.config.settings.get("min_executable_edge_bps", 25))
        notional = float(self.config.risk.get("max_notional_usdt", 250))
        while True:
            started = time.perf_counter()
            cross = detect_cross_venue(
                self.book,
                self.config.markets.get("cross_venue") or [],
                min_alert,
                fee_map,
                extra,
                notional,
            )
            triangles = detect_triangles(
                self.book,
                self.triangles,
                min_exec,
                float(fees.get("binance_taker_bps", 10)),
                extra,
                notional,
            )
            fresh = [opp for opp in (*cross, *triangles) if opp.id not in self.seen]
            for opp in fresh:
                self.seen.add(opp.id)
                self.opportunities.appendleft(opp)
                self.stats.opportunities += 1
                if not opp.executable:
                    continue
                fills = await self.broker.execute(opp)
                for fill in fills:
                    self.fills.appendleft(fill)
                    if fill.status == "blocked":
                        self.stats.live_blocked += 1
            self.stats.scans += 1
            self.stats.quotes = self.book.size()
            self.stats.markets_live = self.book.live_count(
                float(self.config.risk.get("stale_quote_seconds", 8))
            )
            self.stats.last_scan_ms = (time.perf_counter() - started) * 1000
            await self.broadcast()
            await asyncio.sleep(interval)


async def run_engine(engine: Engine) -> None:
    await asyncio.gather(engine.run_feeds(), engine.run_scanner())
