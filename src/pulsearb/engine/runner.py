from __future__ import annotations

import asyncio
import time
from pathlib import Path
from collections import deque

from pulsearb.branding import PRODUCT
from pulsearb.config import SPOT_VENUES, AppConfig
from pulsearb.engine.arbitrage import (
    detect_auto_cross,
    detect_cross_venue,
    detect_quote_dislocations,
    detect_triangles,
    discover_triangles,
)
from pulsearb.engine.book import MarketBook
from pulsearb.engine.broker import Broker, LiveBinanceBroker, LiveRouter, PaperBroker
from pulsearb.engine.coinbase_live import LiveCoinbaseBroker
from pulsearb.engine.desk import KIND_LABELS, TradeDesk
from pulsearb.engine.live_ready import quote_cash
from pulsearb.engine.money import coinbase_live_ok
from pulsearb.engine.report import ProfitLedger
from pulsearb.engine.risk import RiskManager
from pulsearb.engine.trades import group_trades
from pulsearb.feeds.binance import BinanceFeed
from pulsearb.feeds.bitstamp import BitstampFeed
from pulsearb.feeds.coinbase import CoinbaseFeed
from pulsearb.feeds.gemini import GeminiFeed
from pulsearb.feeds.kraken import KrakenFeed
from pulsearb.feeds.simulator import SimulatorFeed
from pulsearb.feeds.yahoo import YahooFeed
from pulsearb.models import EngineStats, Fill, Opportunity
from pulsearb.symbols import canonical_from_pair


def _cooldown_block(fills: list[Fill]) -> bool:
    """True when the desk refused because the same route is still cooling down."""
    if not fills or any(item.status == "filled" for item in fills):
        return False
    return all(item.status == "blocked" for item in fills) and any(
        (item.note or "").strip().lower() == "cooldown" for item in fills
    )


class Engine:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.book = MarketBook()
        self.stats = EngineStats(started_at=time.time())
        self.opportunities: deque[Opportunity] = deque(maxlen=80)
        self.fills: deque[Fill] = deque(maxlen=80)
        self.seen: set[str] = set()
        self.invested: set[str] = set()
        self.by_id: dict[str, Opportunity] = {}
        self.listeners: set[asyncio.Queue] = set()
        min_notional = float(config.risk.get("min_notional_usdt", 1))
        default_size = max(min_notional, min(5.0, config.live_notional()))
        self.desk = TradeDesk(
            notional=default_size,
            max_notional=float(config.risk.get("max_notional_usdt", 250)),
            live_max=float(config.risk.get("live_max_notional_usdt", 25)),
            min_notional=min_notional,
            live=False,
        )
        self._fee_map = config.fee_map()
        self._slippage = float(config.fees.get("extra_slippage_bps", 2))
        self.live_armed = bool(config.live_enabled())
        self.risk = RiskManager(
            max_notional_usdt=float(config.risk.get("max_notional_usdt", 250)),
            min_notional_usdt=min_notional,
            max_open_orders=int(config.risk.get("max_open_orders", 8)),
            daily_loss_limit_usdt=float(config.risk.get("daily_loss_limit_usdt", 100)),
            cooldown_seconds=float(config.risk.get("cooldown_seconds", 8)),
            live_budget_usdt=0.0,
        )
        self.paper = PaperBroker(self.risk)
        self.broker: Broker = self.paper
        self.report = ProfitLedger(Path.cwd() / "data" / "CyberSym-SecureTrade-profit-report.csv")
        self._ensure_live_router()
        self._apply_mode_settings()
        self.triangles_by_venue = {
            venue: discover_triangles(config.symbols(venue))
            for venue in SPOT_VENUES
            if config.symbols(venue)
        }
        self._lock = asyncio.Lock()
        self._balances_at = 0.0

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=8)
        self.listeners.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self.listeners.discard(queue)

    def live_active(self) -> bool:
        return bool(self.live_armed)

    def _ensure_live_router(self) -> bool:
        if isinstance(self.broker, LiveRouter) and (self.broker.coinbase is not None or self.broker.binance is not None):
            self.broker.armed = self.live_armed
            return True
        coinbase_broker = None
        binance_broker = None
        creds = self.config.coinbase_credentials()
        if creds:
            key_name, secret = creds
            coinbase_cfg = self.config.markets.get("coinbase") or {}
            coinbase_broker = LiveCoinbaseBroker(
                risk=self.risk,
                api_key=key_name,
                api_secret=secret,
                paper_fallback=self.paper,
                rest_url=str(coinbase_cfg.get("brokerage_url") or "https://api.coinbase.com"),
            )
        if self.config.binance_live_ready():
            binance = self.config.markets.get("binance") or {}
            rest = binance.get("testnet_rest_url" if self.config.env.binance_testnet else "rest_url")
            binance_broker = LiveBinanceBroker(
                risk=self.risk,
                api_key=self.config.env.binance_api_key,
                api_secret=self.config.env.binance_api_secret,
                rest_url=str(rest),
                paper_fallback=self.paper,
            )
        if coinbase_broker is None and binance_broker is None:
            self.broker = self.paper
            return False
        self.broker = LiveRouter(
            self.paper,
            coinbase=coinbase_broker,
            binance=binance_broker,
            armed=self.live_armed,
        )
        return True

    def _apply_mode_settings(self) -> None:
        live = self.live_armed
        self.desk.live = live
        if live:
            self.desk.auto_invest = False
            if "coinbase" not in self.desk.venues:
                self.desk.venues = ["coinbase", *self.desk.venues]
            for kind in ("dislocation", "triangular"):
                if kind not in self.desk.kinds:
                    self.desk.kinds.append(kind)
            self.risk.max_notional_usdt = float(self.config.risk.get("live_max_notional_usdt", 25))
            self.risk.cooldown_seconds = float(self.config.risk.get("live_cooldown_seconds", 2))
            if self.risk.live_budget_usdt <= 0:
                self.risk.live_budget_usdt = float(
                    self.config.risk.get("live_budget_usdt", self.config.risk.get("live_max_notional_usdt", 25))
                )
            self.desk.notional = self.desk.clamp_notional(self.desk.notional)
        else:
            self.risk.max_notional_usdt = float(self.config.risk.get("max_notional_usdt", 250))
            self.risk.cooldown_seconds = float(self.config.risk.get("cooldown_seconds", 8))

    async def set_execution(self, mode: str, confirm: str = "") -> dict:
        wanted = str(mode or "").strip().lower()
        if wanted not in {"paper", "live"}:
            return {"ok": False, "error": "Choose paper or live."}
        if wanted == "paper":
            self.live_armed = False
            if isinstance(self.broker, LiveRouter):
                self.broker.armed = False
            self._apply_mode_settings()
            await self.broadcast()
            return {
                "ok": True,
                "execution": "paper",
                "desk": self.desk_view(),
                "note": "Paper trading. No real Coinbase orders.",
            }
        if self.config.env.demo_only:
            return {
                "ok": False,
                "error": "The demo scanner has no live Coinbase prices. Close it and use start-live.bat, then switch to Live.",
            }
        if str(confirm or "") != self.config.live_confirm_phrase:
            return {"ok": False, "error": "Confirm that you want real Coinbase orders."}
        from pulsearb.engine.live_ready import assess_live_ready

        report = await assess_live_ready(self.config, killed=self.risk.killed, armed=False)
        if not report.get("ready"):
            return {
                "ok": False,
                "error": report.get("note") or "Live ready check did not pass.",
                "ready": False,
            }
        if not self._ensure_live_router():
            return {"ok": False, "error": "Coinbase key file is missing. Save keys\\coinbase.json, then Check again."}
        self.live_armed = True
        if isinstance(self.broker, LiveRouter):
            self.broker.armed = True
        self._apply_mode_settings()
        await self._refresh_cash()
        await self.broadcast()
        return {
            "ok": True,
            "execution": "live",
            "desk": self.desk_view(),
            "note": "LIVE. Coinbase USD vs USDC dislocations and triangles. Each tap starts in USD and aims to finish in USD.",
        }

    async def _refresh_cash(self) -> None:
        coinbase = getattr(self.broker, "coinbase", None)
        if coinbase is None or not hasattr(coinbase, "refresh_balances"):
            return
        try:
            await coinbase.refresh_balances()
            self._balances_at = time.time()
        except Exception:
            pass

    def snapshot(self) -> dict:
        quotes = sorted(self.book.snapshot(), key=lambda q: (q.venue, q.native_symbol))
        live = self.live_active()
        live_pnl = float(getattr(self.broker, "live_pnl", 0.0))
        venues = "+".join(getattr(self.broker, "live_venues", None) or self.config.live_venue_names())
        execution = f"live {venues}".strip() if live else "paper"
        balances = getattr(self.broker, "balances", {}) or {}
        cash_usd = quote_cash(balances)
        kill_paused = bool(self.risk.killed and live)
        fill_list = list(self.fills)[:80]
        if kill_paused:
            live_note = (
                "LIVE is still on. Kill switch paused new orders. Click Resume. You are not back on paper."
            )
        elif live:
            live_note = (
                "LIVE Coinbase dislocations: USD vs USDC books, plus same-exchange triangles. "
                "Each tap buys with USD and aims to finish back in USD. Not buy-and-hold. "
                "Cross-venue (Coinbase vs Kraken) stays paper — that would mean holding coins to move them. "
                "Each tap is your desk size. Session budget is the $25 cap."
            )
        else:
            live_note = ""
        return {
            "stats": {
                **self.stats.to_dict(),
                "paper_pnl": round(self.paper.pnl + live_pnl, 4),
                "live_pnl": round(live_pnl, 4),
                "killed": self.risk.killed,
                "kill_paused": kill_paused,
                "execution": execution,
                "live_armed": live,
                "uptime_s": round(time.time() - self.stats.started_at, 1),
                "triangles": sum(1 for item in self.opportunities if item.kind.value == "triangular"),
                "report_rows": self.report.taken_rows,
                "report_path": str(self.report.csv_path) if self.report.csv_path else "",
                "balances": {str(k): round(float(v), 8) for k, v in balances.items() if float(v) > 0},
                "cash_usd": round(cash_usd, 2),
                "live_note": live_note,
                "live_notional": self.desk.notional,
            },
            "desk": self.desk_view(),
            "quotes": [q.to_dict() for q in quotes if self.desk.quote_ok(q, self.book)],
            "opportunities": [self._opp_view(o) for o in list(self.opportunities)[:40]],
            "fills": [f.to_dict() for f in fill_list],
            "trades": group_trades(fill_list),
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

    def _opp_view(self, opp: Opportunity) -> dict:
        data = opp.to_dict()
        live_ok = coinbase_live_ok(opp)
        paper_only = self.live_active() and not live_ok
        pending = (
            opp.executable
            and opp.id not in self.invested
            and self.desk.matches(opp, self.book)
            and not self.risk.killed
            and not paper_only
        )
        data.update(
            {
                "kind_label": KIND_LABELS.get(opp.kind.value, opp.kind.value),
                "expected_pnl": round(self.desk.notional * opp.net_edge_bps / 10_000, 4),
                "notional": self.desk.notional,
                "pending": pending,
                "investable": pending and not self.desk.auto_invest,
                "chosen": self.desk.matches(opp, self.book),
                "live_ok": live_ok,
                "paper_only": paper_only,
            }
        )
        return data

    def desk_view(self) -> dict:
        data = self.desk.to_dict()
        left = self.risk.remaining_budget()
        data.update(
            {
                "budget": self.risk.live_budget_usdt or None,
                "budget_left": left,
                "taps_left": self.risk.taps_left(self.desk.notional),
            }
        )
        return data

    def apply_desk(self, payload: dict) -> dict:
        self.desk.live = self.live_active()
        self.desk.apply(payload)
        return self.desk_view()

    async def invest(self, opportunity_id: str) -> dict:
        opp = self.by_id.get(opportunity_id)
        if opp is None:
            return {"ok": False, "error": "That trade is no longer on the board."}
        if not opp.executable:
            return {"ok": False, "error": "That row is watch-only (delayed data)."}
        if not self.desk.matches(opp, self.book):
            return {"ok": False, "error": "That pair is outside your price filter, or that coin/exchange is off."}
        if opportunity_id in self.invested:
            return {"ok": False, "error": "You already took this trade."}
        if self.live_active() and not coinbase_live_ok(opp):
            return {
                "ok": False,
                "error": "Live only takes Coinbase dislocations that buy with USD and sell back toward USD. Cross-exchange gaps stay paper.",
            }
        fills = await self._take(opp)
        await self.broadcast()
        if not any(item.status == "filled" for item in fills):
            note = next((item.note for item in fills if item.note), "Could not complete the buy and sell.")
            return {
                "ok": False,
                "error": note,
                "fills": [fill.to_dict() for fill in fills],
                "desk": self.desk_view(),
            }
        return {"ok": True, "fills": [fill.to_dict() for fill in fills], "desk": self.desk_view()}

    async def _take(self, opp: Opportunity) -> list[Fill]:
        opp.notional = self.desk.notional
        fills = await self.broker.execute(opp)
        if _cooldown_block(fills):
            return fills
        if any(item.status == "filled" for item in fills):
            self.invested.add(opp.id)
        for fill in fills:
            self.fills.appendleft(fill)
            if fill.status == "blocked":
                self.stats.live_blocked += 1
        self.report.record_opportunity(
            opp,
            fills,
            paper=all(fill.paper for fill in fills) if fills else self.broker.paper,
            killed=self.risk.killed,
            fee_map=self._fee_map,
            slippage_bps=self._slippage,
        )
        await self._refresh_cash()
        return fills

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
        fee_map = self._fee_map
        extra = self._slippage
        min_alert = float(self.config.settings.get("min_edge_bps", 8))
        min_exec = float(self.config.settings.get("min_executable_edge_bps", 25))
        stale = float(self.config.risk.get("stale_quote_seconds", 8))
        max_raw = float(self.config.settings.get("max_raw_edge_bps", 300))
        max_skew = float(self.config.settings.get("max_quote_skew_seconds", 1.5))
        while True:
            started = time.perf_counter()
            notional = self.desk.notional
            cross = detect_cross_venue(
                self.book,
                self.config.markets.get("cross_venue") or [],
                min_alert,
                fee_map,
                extra,
                notional,
                max_raw_edge_bps=max_raw,
                max_quote_age=stale,
                max_quote_skew=max_skew,
            )
            auto = detect_auto_cross(
                self.book,
                self.config.usd_equivalents,
                min_alert,
                fee_map,
                extra,
                notional,
                stale_seconds=stale,
                max_raw_edge_bps=max_raw,
                max_quote_skew=max_skew,
            )
            triangles: list[Opportunity] = []
            for venue, tri in self.triangles_by_venue.items():
                taker = fee_map.get(venue, 26)
                scan_venue = venue
                triangles.extend(
                    detect_triangles(
                        self.book,
                        tri,
                        min_alert,
                        taker,
                        extra,
                        notional,
                        venue=scan_venue,
                        min_executable_edge_bps=min_exec,
                        max_raw_edge_bps=max_raw,
                        max_quote_age=stale,
                        max_quote_skew=max_skew,
                    )
                )
            dislocations = detect_quote_dislocations(
                self.book,
                venue="coinbase",
                min_edge_bps=min_alert,
                fee_map=fee_map,
                extra_slippage_bps=extra,
                notional=notional,
                min_executable_edge_bps=min_exec,
                max_raw_edge_bps=max_raw,
                max_quote_age=stale,
                max_quote_skew=max_skew,
            )
            # Demo quotes use real venue names, so the venue-scoped scan above is enough.
            current = [*cross, *auto, *triangles, *dislocations]
            for opp in current:
                self.by_id[opp.id] = opp
                if opp.id in self.seen:
                    continue
                self.seen.add(opp.id)
                if len(self.by_id) > 2000:
                    self.by_id = {item.id: item for item in self.opportunities}
                    self.by_id[opp.id] = opp
                self.opportunities.appendleft(opp)
                self.stats.opportunities += 1
            if (
                self.desk.auto_invest
                and not self.desk.live
                and not self.live_active()
                and not self.risk.killed
                and self.risk.allow(self.desk.notional).allowed
            ):
                candidates = [
                    opp
                    for opp in current
                    if opp.executable and self.desk.matches(opp, self.book)
                ]
                if candidates:
                    best = max(candidates, key=lambda item: item.net_edge_bps)
                    await self._take(best)
            now = time.time()
            if now - self._balances_at > 30:
                await self._refresh_cash()
            self.stats.scans += 1
            self.stats.quotes = self.book.size()
            self.stats.markets_live = self.book.live_count(stale)
            self.stats.last_scan_ms = (time.perf_counter() - started) * 1000
            await self.broadcast()
            await asyncio.sleep(interval)


async def run_engine(engine: Engine) -> None:
    coinbase = getattr(engine.broker, "coinbase", None)
    if coinbase is not None and hasattr(coinbase, "refresh_balances"):
        balances = await coinbase.refresh_balances()
        engine._balances_at = time.time()
        shown = ", ".join(
            f"{asset} {amount:.6g}" for asset, amount in list(balances.items())[:8]
        ) or "(empty)"
        print(f"{PRODUCT} Coinbase account: {shown}")
    await asyncio.gather(engine.run_feeds(), engine.run_scanner())
