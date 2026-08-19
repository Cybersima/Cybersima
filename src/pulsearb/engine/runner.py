from __future__ import annotations

import asyncio
import time
from pathlib import Path
from collections import deque

from pulsearb.config import SPOT_VENUES, AppConfig
from pulsearb.engine.arbitrage import detect_auto_cross, detect_cross_venue, detect_triangles, discover_triangles
from pulsearb.engine.book import MarketBook
from pulsearb.engine.broker import Broker, LiveBinanceBroker, PaperBroker
from pulsearb.engine.report import ProfitLedger
from pulsearb.engine.risk import RiskManager
from pulsearb.feeds.binance import BinanceFeed
from pulsearb.feeds.bitstamp import BitstampFeed
from pulsearb.feeds.coinbase import CoinbaseFeed
from pulsearb.feeds.gemini import GeminiFeed
from pulsearb.feeds.kraken import KrakenFeed
from pulsearb.feeds.simulator import SimulatorFeed
from pulsearb.feeds.yahoo import YahooFeed
from pulsearb.models import EngineStats, Fill, Opportunity
from pulsearb.symbols import canonical_from_pair


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
        self.report = ProfitLedger(Path("data") / "CyberSym-SecureTrade-profit-report.csv")
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
        self.triangles_by_venue = {
            venue: discover_triangles(config.symbols(venue))
            for venue in SPOT_VENUES
            if config.symbols(venue)
        }
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
                "triangles": sum(len(items) for items in self.triangles_by_venue.values()),
                "report_rows": len(self.report.rows),
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

    def _demo_instruments(self) -> list[tuple[str, str, bool]]:
        rows: list[tuple[str, str, bool]] = []
        for venue in SPOT_VENUES:
            if venue == "binance" and not self.config.env.enable_binance:
                continue
            for symbol in self.config.symbols(venue):
                try:
                    canon = canonical_from_pair(symbol)
                except ValueError:
                    continue
                rows.append((venue, canon, True))
        for row in self.config.yahoo_symbols:
            rows.append(("yahoo", row["canonical"], False))
        return rows

    async def run_feeds(self) -> None:
        tasks = []
        markets = self.config.markets
        settings = self.config.settings
        sim = settings.get("simulator") or {}
        demo_only = self.config.env.demo_only

        if sim.get("enabled", False) or demo_only:
            tasks.append(
                SimulatorFeed(
                    instruments=self._demo_instruments(),
                    inject_gaps=bool(sim.get("inject_gaps", True)),
                    gap_every_seconds=float(sim.get("gap_every_seconds", 18)),
                ).run(self.book, self.stats.feed_status)
            )
        if not demo_only:
            if self.config.venue_enabled("coinbase"):
                cfg = markets["coinbase"]
                tasks.append(
                    CoinbaseFeed(
                        symbols=self.config.symbols("coinbase"),
                        rest_url=str(cfg.get("rest_url")),
                        ws_url=str(cfg.get("ws_url")),
                        poll_seconds=float(cfg.get("poll_seconds") or settings.get("coinbase_poll_seconds", 1.0)),
                    ).run(self.book, self.stats.feed_status)
                )
            if self.config.venue_enabled("kraken"):
                cfg = markets["kraken"]
                tasks.append(
                    KrakenFeed(
                        symbols=self.config.symbols("kraken"),
                        rest_url=str(cfg.get("rest_url")),
                        poll_seconds=float(cfg.get("poll_seconds") or settings.get("kraken_poll_seconds", 1.0)),
                    ).run(self.book, self.stats.feed_status)
                )
            if self.config.venue_enabled("gemini"):
                cfg = markets["gemini"]
                tasks.append(
                    GeminiFeed(
                        symbols=self.config.symbols("gemini"),
                        rest_url=str(cfg.get("rest_url")),
                        poll_seconds=float(cfg.get("poll_seconds") or settings.get("gemini_poll_seconds", 1.0)),
                    ).run(self.book, self.stats.feed_status)
                )
            if self.config.venue_enabled("bitstamp"):
                cfg = markets["bitstamp"]
                tasks.append(
                    BitstampFeed(
                        symbols=self.config.symbols("bitstamp"),
                        rest_url=str(cfg.get("rest_url")),
                        poll_seconds=float(cfg.get("poll_seconds") or settings.get("bitstamp_poll_seconds", 1.0)),
                    ).run(self.book, self.stats.feed_status)
                )
            if self.config.venue_enabled("binance"):
                cfg = markets["binance"]
                rest = cfg.get("testnet_rest_url" if self.config.env.binance_testnet else "rest_url")
                ws = cfg.get("testnet_ws_url" if self.config.env.binance_testnet else "ws_url")
                tasks.append(
                    BinanceFeed(
                        symbols=self.config.binance_symbols,
                        rest_url=str(rest),
                        ws_url=str(ws),
                        rest_poll_seconds=float(settings.get("binance_rest_poll_seconds", 1.0)),
                    ).run(self.book, self.stats.feed_status)
                )
            if self.config.venue_enabled("yahoo"):
                cfg = markets["yahoo"]
                tasks.append(
                    YahooFeed(
                        symbols=self.config.yahoo_symbols,
                        poll_seconds=float(cfg.get("poll_seconds") or settings.get("yahoo_poll_seconds", 2.0)),
                    ).run(self.book, self.stats.feed_status)
                )
        if not tasks:
            raise RuntimeError("No market feeds enabled")
        await asyncio.gather(*tasks)

    async def run_scanner(self) -> None:
        interval = self.config.scan_interval_ms / 1000.0
        fee_map = self.config.fee_map()
        extra = float(self.config.fees.get("extra_slippage_bps", 2))
        min_alert = float(self.config.settings.get("min_edge_bps", 8))
        min_exec = float(self.config.settings.get("min_executable_edge_bps", 25))
        notional = float(self.config.risk.get("max_notional_usdt", 250))
        stale = float(self.config.risk.get("stale_quote_seconds", 8))
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
            auto = detect_auto_cross(
                self.book,
                self.config.usd_equivalents,
                min_alert,
                fee_map,
                extra,
                notional,
                stale_seconds=stale,
            )
            triangles: list[Opportunity] = []
            for venue, tri in self.triangles_by_venue.items():
                taker = fee_map.get(venue, 26)
                scan_venue = venue
                triangles.extend(
                    detect_triangles(
                        self.book,
                        tri,
                        min_exec,
                        taker,
                        extra,
                        notional,
                        venue=scan_venue,
                    )
                )
            # Demo quotes use real venue names, so the venue-scoped scan above is enough.
            fresh = [opp for opp in (*cross, *auto, *triangles) if opp.id not in self.seen]
            for opp in fresh:
                self.seen.add(opp.id)
                self.opportunities.appendleft(opp)
                self.stats.opportunities += 1
                fills: list[Fill] = []
                if opp.executable:
                    fills = await self.broker.execute(opp)
                    for fill in fills:
                        self.fills.appendleft(fill)
                        if fill.status == "blocked":
                            self.stats.live_blocked += 1
                self.report.record_opportunity(
                    opp,
                    fills,
                    paper=self.broker.paper,
                    killed=self.risk.killed,
                    fee_map=fee_map,
                    slippage_bps=extra,
                )
            self.stats.scans += 1
            self.stats.quotes = self.book.size()
            self.stats.markets_live = self.book.live_count(stale)
            self.stats.last_scan_ms = (time.perf_counter() - started) * 1000
            await self.broadcast()
            await asyncio.sleep(interval)


async def run_engine(engine: Engine) -> None:
    await asyncio.gather(engine.run_feeds(), engine.run_scanner())
