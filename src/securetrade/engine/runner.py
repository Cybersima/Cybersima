from __future__ import annotations

import asyncio
import time
from collections import deque

from securetrade.config import SPOT_VENUES, AppConfig
from securetrade.engine.arbitrage import detect_auto_cross, detect_cross_venue, detect_triangles, discover_triangles
from securetrade.engine.book import MarketBook
from securetrade.engine.broker import Broker, LiveBinanceBroker, PaperBroker
from securetrade.engine.capital import CapitalProtection
from securetrade.engine.guardian import Guardian
from securetrade.engine.health import HealthMonitor
from securetrade.engine.market_colors import latest_tones, pair_key
from securetrade.engine.paper_lab import PaperLab
from securetrade.engine.pipeline import TradingPipeline
from securetrade.engine.risk import RiskManager
from securetrade.engine.starter import get_rung, ladder_public
from securetrade.engine.takeover import TakeoverGuard
from securetrade.engine.why import customer_details
from securetrade.feeds.binance import BinanceFeed
from securetrade.feeds.bitstamp import BitstampFeed
from securetrade.feeds.coinbase import CoinbaseFeed
from securetrade.feeds.gemini import GeminiFeed
from securetrade.feeds.kraken import KrakenFeed
from securetrade.feeds.simulator import SimulatorFeed
from securetrade.feeds.yahoo import YahooFeed
from securetrade.journal import DecisionJournal
from securetrade.models import (
    CommitDecision,
    EngineStats,
    Fill,
    KillSource,
    OperatingMode,
    Opportunity,
    PaperOutcome,
    PaperPosition,
)
from securetrade.symbols import canonical_from_pair, split_pair


class Engine:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.book = MarketBook()
        equity = config.starting_equity
        self.stats = EngineStats(started_at=time.time(), account_value=equity, peak_equity=equity)
        self.opportunities: deque[Opportunity] = deque(maxlen=80)
        self.fills: deque[Fill] = deque(maxlen=80)
        self.seen: set[str] = set()
        self.listeners: set[asyncio.Queue] = set()
        self.risk = RiskManager(
            max_notional_usdt=float(config.risk.get("max_notional_usdt", 250)),
            max_open_orders=int(config.risk.get("max_open_orders", 4)),
            daily_loss_limit_usdt=float(config.risk.get("daily_loss_limit_usdt", 150)),
            cooldown_seconds=float(config.risk.get("cooldown_seconds", 8)),
            max_drawdown_pct=float(config.risk.get("max_drawdown_pct", 5)),
        )
        self.risk.peak_equity = equity
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
        self.journal = DecisionJournal()
        self.capital = CapitalProtection({**config.capital, "account_value": equity})
        self.paper_lab = PaperLab(timeout_seconds=float(config.settings.get("paper", {}).get("capture_timeout_seconds", 12)))
        self.pipeline = TradingPipeline(
            guardian=Guardian(config.guardian),
            capital=self.capital,
            journal=self.journal,
            paper_lab=self.paper_lab,
            mode=config.operating_mode,
        )
        self.health = HealthMonitor()
        self.takeover = TakeoverGuard()
        self.alerts: deque[dict] = deque(maxlen=50)
        self.pending: dict[str, Opportunity] = {}
        self.auto_trading = config.operating_mode is OperatingMode.AUTO and get_rung(config.starter_rung).allow_auto
        self.triangles_by_venue = {
            venue: discover_triangles(config.symbols(venue))
            for venue in SPOT_VENUES
            if config.symbols(venue)
        }
        self._lock = asyncio.Lock()
        self.takeover.observe("command-center", "127.0.0.1", "local")

    def set_mode(self, mode: OperatingMode) -> dict:
        rung = get_rung(self.config.starter_rung)
        if mode is OperatingMode.AUTO and not rung.allow_auto:
            self.pipeline.mode = OperatingMode.ASSIST if rung.allow_live else OperatingMode.LEARN
            self.config.settings["operating_mode"] = self.pipeline.mode.value
            self.auto_trading = False
            return {
                "ok": False,
                "mode": self.pipeline.mode.value,
                "reason": "Auto stays off on the Starter ladder. Use Assist after paper, or keep Learn.",
            }
        self.pipeline.mode = mode
        self.config.settings["operating_mode"] = mode.value
        self.auto_trading = mode is OperatingMode.AUTO
        return {"ok": True, "mode": mode.value}

    def apply_starter(self, rung_id: str) -> dict:
        self.config.apply_rung(rung_id)
        rung = get_rung(rung_id)
        equity = rung.equity
        self.stats.account_value = equity
        self.stats.peak_equity = equity
        self.risk.max_notional_usdt = rung.max_ticket
        self.risk.daily_loss_limit_usdt = rung.daily_loss
        self.risk.max_drawdown_pct = rung.max_drawdown_pct
        self.risk.peak_equity = equity
        self.risk.realized_pnl = 0.0
        self.capital.max_trade_size = rung.max_ticket
        self.capital.max_position_exposure = rung.max_ticket
        self.capital.max_daily_loss = rung.daily_loss
        self.capital.max_drawdown_pct = rung.max_drawdown_pct
        self.capital.account_value = equity
        self.capital.daily_pnl = 0.0
        self.set_mode(rung.default_mode)
        self.auto_trading = False
        return {"ok": True, "rung": rung.id, "equity": equity, "max_ticket": rung.max_ticket}

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=8)
        self.listeners.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self.listeners.discard(queue)

    def snapshot(self) -> dict:
        quotes = sorted(self.book.snapshot(), key=lambda q: (q.venue, q.native_symbol))
        ranked = sorted(self.opportunities, key=lambda o: o.quality_score, reverse=True)
        best = next((o for o in ranked if o.guardian_allowed), ranked[0] if ranked else None)
        health = self.health.report(self.stats.feed_status, stale_feeds=[])
        security_score = 98 if health.ok and not self.takeover.suspended else 72
        self.stats.security_score = security_score
        drawdown = 0.0
        if self.stats.peak_equity:
            drawdown = max(0.0, (self.stats.peak_equity - self.stats.account_value) / self.stats.peak_equity * 100)
        self.stats.max_drawdown = drawdown
        closed = [p.to_dict() for p in list(self.paper_lab.closed)[:40]]
        tones = latest_tones(list(self.paper_lab.closed))
        return {
            "stats": {
                **self.stats.to_dict(),
                "paper_pnl": round(self.paper.pnl, 4),
                "killed": self.risk.killed,
                "kill_source": self.risk.kill_source,
                "execution": "live" if self.config.live_enabled() else "paper",
                "operating_mode": self.pipeline.mode.value,
                "auto_trading": self.auto_trading and not self.risk.killed,
                "uptime_s": round(time.time() - self.stats.started_at, 1),
                "triangles": sum(len(items) for items in self.triangles_by_venue.values()),
                "edition": self.config.edition,
                "system": "PROTECTED" if not self.takeover.suspended else "SUSPENDED",
                "trading": "ACTIVE" if not self.risk.killed else "STOPPED",
                "daily_loss_limit": float(self.config.risk.get("daily_loss_limit_usdt", 5)),
                "today_pnl": round(self.stats.today_pnl, 2),
                "month_pnl": round(self.stats.month_pnl, 2),
                "account_value": round(self.stats.account_value, 2),
                "max_drawdown": round(drawdown, 2),
                "handoff_atomic_ready": self.stats.handoff_atomic_ready,
                "recovery_commit_pass": self.stats.recovery_commit_pass,
                "recovery_research_pass": self.stats.recovery_research_pass,
                "paper_opened": self.stats.paper_opened,
                "starter_rung": self.config.starter_rung,
                "max_ticket": float(self.config.ticket_size),
            },
            "quotes": [
                {**q.to_dict(), "tone": tones.get(pair_key(q.canonical), "")}
                for q in quotes
            ],
            "opportunities": [o.to_dict() for o in list(ranked)[:40]],
            "best": best.to_dict() if best else None,
            "best_details": customer_details(best) if best else None,
            "starter": {
                "rung": self.config.starter_rung,
                "ladder": ladder_public(),
                "allow_auto": get_rung(self.config.starter_rung).allow_auto,
                "allow_live": get_rung(self.config.starter_rung).allow_live,
            },
            "fills": [f.to_dict() for f in list(self.fills)[:40]],
            "paper_lab": closed,
            "open_paper": [p.to_dict() for p in self.paper_lab.open.values()],
            "recovery_commit": [c.to_dict() for c in self.pipeline.commits[-40:]],
            "journal": [e.to_dict() for e in list(self.journal.entries)[:40]],
            "alerts": list(self.alerts)[:20],
            "health": health.to_dict(),
            "pending": [o.to_dict() for o in self.pending.values()],
            "live_prerequisites": self.config.live_prerequisites(),
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
        demo_only = self.config.env.demo_only or self.config.env.pulse_demo_only

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

    def _enrich_pair(self, opp: Opportunity) -> Opportunity:
        pair = opp.pair
        if not pair and opp.legs:
            try:
                base, quote = split_pair(opp.legs[0].symbol)
                pair = f"{base}/{quote if quote != 'USD' else 'USDC'}"
            except ValueError:
                pair = opp.legs[0].symbol
        return opp.with_updates(pair=pair)

    async def ingest(self, opp: Opportunity, *, force_outcome: PaperOutcome | None = None, force_pnl: float | None = None) -> PipelineResultWrapper:
        opp = self._enrich_pair(opp)
        result = self.pipeline.evaluate(opp, self.book)
        self.opportunities.appendleft(result.opportunity)
        self.stats.opportunities += 1
        if result.blocked:
            self.stats.guardian_blocks += 1
            self.alerts.appendleft(
                {
                    "type": "guardian_block",
                    "severity": "CRITICAL",
                    "title": "EXECUTION BLOCKED",
                    "reasons": result.opportunity.why_blocked,
                    "opportunity_id": result.opportunity.id,
                    "ts": time.time(),
                }
            )
            return PipelineResultWrapper(result, [])
        if result.pending_approval:
            self.pending[result.opportunity.id] = result.opportunity
            return PipelineResultWrapper(result, [])
        if result.handoff == "ATOMIC_READY":
            self.stats.handoff_atomic_ready += 1
        fills: list[Fill] = []
        if result.commit:
            if result.commit.decision == CommitDecision.COMMIT.value:
                self.stats.recovery_commit_pass += 1
            elif result.commit.decision == CommitDecision.RESEARCH_COMMIT.value:
                self.stats.recovery_research_pass += 1
            else:
                self.stats.recovery_cancel += 1
        if result.position:
            self.stats.paper_opened += 1
            if self.pipeline.mode is not OperatingMode.LEARN or True:
                fills = await self.broker.execute(result.opportunity)
                for fill in fills:
                    self.fills.appendleft(fill)
                    if fill.status == "blocked":
                        self.stats.live_blocked += 1
            if force_outcome:
                closed = self.pipeline.close_forced(
                    result.opportunity.id,
                    force_outcome,
                    force_pnl if force_pnl is not None else result.position.expected_pnl,
                )
                self._apply_closed(closed)
            else:
                live_edge = result.opportunity.expected_net_edge_bps
                closed = self.paper_lab.resolve_against_edge(result.opportunity.id, live_edge)
                if closed:
                    self.pipeline.journal.record(
                        action="paper_lab_close",
                        opportunity_id=closed.opportunity_id,
                        decision=closed.outcome,
                        sources=[],
                        expected_profit=closed.expected_pnl,
                        actual_result=closed.actual_pnl,
                        risk_score=closed.trust_score,
                        security_decision=closed.outcome,
                        details=closed.to_dict(),
                    )
                    self._apply_closed(closed)
        await self.broadcast()
        return PipelineResultWrapper(result, fills)

    def _apply_closed(self, closed: PaperPosition) -> None:
        self.paper.realize(closed.actual_pnl)
        self.stats.today_pnl += closed.actual_pnl
        self.stats.month_pnl += closed.actual_pnl
        self.stats.account_value += closed.actual_pnl
        self.stats.peak_equity = max(self.stats.peak_equity, self.stats.account_value)
        self.capital.record(closed.actual_pnl, -closed.notional)
        if closed.outcome == PaperOutcome.CAPTURED.value:
            self.stats.captured += 1
        elif closed.outcome == PaperOutcome.REVERSED.value:
            self.stats.reversed += 1
        elif closed.outcome == PaperOutcome.MISSED.value:
            self.stats.missed += 1
        elif closed.outcome == PaperOutcome.EXPIRED.value:
            self.stats.expired += 1

    async def approve(self, opportunity_id: str) -> dict:
        opp = self.pending.pop(opportunity_id, None)
        if not opp:
            return {"ok": False, "reason": "not pending"}
        self.pipeline.approve(opportunity_id)
        wrapped = await self.ingest(opp)
        return {"ok": True, "handoff": wrapped.result.handoff, "commit": wrapped.result.commit.to_dict() if wrapped.result.commit else None}

    async def force_outcome(self, kind: str) -> PaperPosition:
        """End-to-end forced Paper Lab closures used by the validation suite."""
        from securetrade.engine.forced import make_forced_opportunity

        if kind == "cancel":
            opp = make_forced_opportunity(self.book, "cancel")
            wrapped = await self.ingest(opp)
            assert wrapped.result.commit and wrapped.result.commit.decision == CommitDecision.CANCEL.value
            assert wrapped.result.position is None
            return PaperPosition(
                opportunity_id=opp.id,
                pair=opp.pair,
                notional=opp.notional,
                expected_pnl=0,
                actual_pnl=0,
                outcome=PaperOutcome.CANCELLED.value,
                commit_kind=CommitDecision.CANCEL.value,
                opened_at=time.time(),
            )
        mapping = {
            "captured": (PaperOutcome.CAPTURED, 0.31),
            "reversed": (PaperOutcome.REVERSED, -0.20),
            "research": (PaperOutcome.CAPTURED, 0.15),
        }
        outcome, pnl = mapping[kind]
        opp = make_forced_opportunity(self.book, kind)
        if kind == "research":
            # Low confidence → RESEARCH_COMMIT still enters Paper Lab.
            opp = opp.with_updates(execution_confidence=0.4)
        wrapped = await self.ingest(opp, force_outcome=outcome, force_pnl=pnl)
        assert wrapped.result.position is not None
        closed = next(p for p in self.paper_lab.closed if p.opportunity_id == opp.id)
        return closed

    async def run_scanner(self) -> None:
        interval = self.config.scan_interval_ms / 1000.0
        fee_map = self.config.fee_map()
        extra = float(self.config.fees.get("extra_slippage_bps", 2))
        min_alert = float(self.config.settings.get("min_edge_bps", 8))
        min_exec = float(self.config.settings.get("min_executable_edge_bps", 25))
        notional = min(float(self.config.ticket_size), max(0.0, self.stats.account_value))
        stale = float(self.config.risk.get("stale_quote_seconds", 8))
        while True:
            started = time.perf_counter()
            if self.takeover.suspended and self.auto_trading:
                self.risk.kill(KillSource.SECURITY)
                self.alerts.appendleft({"type": "takeover", "title": "Auto trading suspended", "reasons": [self.takeover.reason], "ts": time.time()})
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
                triangles.extend(
                    detect_triangles(
                        self.book,
                        tri,
                        min_exec,
                        taker,
                        extra,
                        notional,
                        venue=venue,
                    )
                )
            fresh = [opp for opp in (*cross, *auto, *triangles) if opp.id not in self.seen]
            for opp in fresh:
                self.seen.add(opp.id)
                if self.risk.killed:
                    continue
                await self.ingest(opp)
            for expired in self.paper_lab.expire_open():
                self._apply_closed(expired)
            report = self.health.report(
                self.stats.feed_status,
                stale_feeds=[q.venue for q in self.book.snapshot() if time.time() - q.ts > stale][:6],
            )
            if report.issues and not self.risk.killed:
                if "stale price feed" in report.issues or "exchange disconnect" in report.issues:
                    self.risk.kill(KillSource.HEALTH)
            self.stats.scans += 1
            self.stats.quotes = self.book.size()
            self.stats.markets_live = self.book.live_count(stale)
            self.stats.last_scan_ms = (time.perf_counter() - started) * 1000
            await self.broadcast()
            await asyncio.sleep(interval)


class PipelineResultWrapper:
    def __init__(self, result, fills: list[Fill]) -> None:
        self.result = result
        self.fills = fills


async def run_engine(engine: Engine) -> None:
    await asyncio.gather(engine.run_feeds(), engine.run_scanner())
