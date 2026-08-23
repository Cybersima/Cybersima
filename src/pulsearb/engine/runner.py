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
from pulsearb.engine.desk import KIND_LABELS, SITE_HIDDEN_VENUES, TradeDesk
from pulsearb.engine.gemini_live import LiveGeminiBroker
from pulsearb.engine.kraken_live import LiveKrakenBroker
from pulsearb.engine.live_ready import quote_cash, usd_spendable
from pulsearb.engine.money import auto_route_ok, live_exec_ok, venue_maker_bps
from pulsearb.engine.oanda_live import LiveOandaBroker
from pulsearb.engine.robinhood_live import LiveRobinhoodBroker
from pulsearb.engine.report import ProfitLedger
from pulsearb.engine.risk import RiskManager
from pulsearb.engine.schedule import window_open
from pulsearb.engine.trades import group_trades
from pulsearb.feeds.binance import BinanceFeed
from pulsearb.feeds.coinbase import CoinbaseFeed
from pulsearb.feeds.gemini import GeminiFeed
from pulsearb.feeds.kraken import KrakenFeed
from pulsearb.feeds.simulator import SimulatorFeed
from pulsearb.feeds.oanda import OandaFeed
from pulsearb.feeds.robinhood import RobinhoodFeed
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
        names = self.config.live_venue_names()
        if names and self.desk.live_venue not in names:
            self.desk.live_venue = names[0]
        self._apply_mode_settings()
        self.triangles_by_venue = {
            venue: discover_triangles(config.symbols(venue))
            for venue in SPOT_VENUES
            if config.symbols(venue)
        }
        self._lock = asyncio.Lock()
        self._balances_at = 0.0
        self.last_block: dict | None = None

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=8)
        self.listeners.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self.listeners.discard(queue)

    def live_active(self) -> bool:
        return bool(self.live_armed)

    def _ensure_live_router(self) -> bool:
        if isinstance(self.broker, LiveRouter) and (
            self.broker.coinbase is not None
            or self.broker.kraken is not None
            or self.broker.binance is not None
            or self.broker.oanda is not None
            or self.broker.gemini is not None
            or self.broker.robinhood is not None
        ):
            self.broker.armed = self.live_armed
            self.broker.live_venue = self.desk.live_venue
            return self._broker_for_live() is not None
        coinbase_broker = None
        kraken_broker = None
        binance_broker = None
        oanda_broker = None
        gemini_broker = None
        robinhood_broker = None
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
                maker_exits=self.config.maker_exits(),
                maker_wait_seconds=self.config.maker_wait_seconds(),
            )
        kraken_creds = self.config.kraken_credentials()
        if kraken_creds:
            key_name, secret = kraken_creds
            kraken_cfg = self.config.markets.get("kraken") or {}
            kraken_broker = LiveKrakenBroker(
                risk=self.risk,
                api_key=key_name,
                api_secret=secret,
                paper_fallback=self.paper,
                rest_url=str(kraken_cfg.get("rest_url") or "https://api.kraken.com"),
                maker_exits=self.config.maker_exits(),
                maker_wait_seconds=self.config.maker_wait_seconds(),
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
        oanda_creds = self.config.oanda_credentials()
        if oanda_creds:
            account_id, access_token, environment = oanda_creds
            oanda_broker = LiveOandaBroker(
                risk=self.risk,
                account_id=account_id,
                access_token=access_token,
                paper_fallback=self.paper,
                environment=environment,
            )
        gemini_creds = self.config.gemini_credentials()
        if gemini_creds:
            key_name, secret = gemini_creds
            gemini_cfg = self.config.markets.get("gemini") or {}
            gemini_broker = LiveGeminiBroker(
                risk=self.risk,
                api_key=key_name,
                api_secret=secret,
                paper_fallback=self.paper,
                rest_url=str(gemini_cfg.get("rest_url") or "https://api.gemini.com"),
            )
        robinhood_creds = self.config.robinhood_credentials()
        if robinhood_creds:
            api_key, private_key = robinhood_creds
            robinhood_broker = LiveRobinhoodBroker(
                risk=self.risk,
                api_key=api_key,
                private_key_base64=private_key,
                paper_fallback=self.paper,
            )
        if (
            coinbase_broker is None
            and kraken_broker is None
            and binance_broker is None
            and oanda_broker is None
            and gemini_broker is None
            and robinhood_broker is None
        ):
            self.broker = self.paper
            return False
        self.broker = LiveRouter(
            self.paper,
            coinbase=coinbase_broker,
            kraken=kraken_broker,
            binance=binance_broker,
            oanda=oanda_broker,
            gemini=gemini_broker,
            robinhood=robinhood_broker,
            armed=self.live_armed,
            live_venue=self.desk.live_venue,
        )
        return self._broker_for_live() is not None

    def _broker_for_live(self):
        if not isinstance(self.broker, LiveRouter):
            return None
        return getattr(self.broker, self.desk.live_venue, None)

    def _apply_mode_settings(self) -> None:
        live = self.live_armed
        self.desk.live = live
        if isinstance(self.broker, LiveRouter):
            self.broker.live_venue = self.desk.live_venue
        if live:
            if not self.desk.schedule_enabled:
                self.desk.auto_invest = False
            if self.desk.live_venue not in self.desk.venues:
                self.desk.venues = [self.desk.live_venue, *self.desk.venues]
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
                "note": "Paper trading. No real exchange orders.",
            }
        if self.config.env.demo_only:
            return {
                "ok": False,
                "error": "The demo scanner has no live prices. Close it and use start-live.bat, then switch to Live.",
            }
        if str(confirm or "") != self.config.live_confirm_phrase:
            return {"ok": False, "error": "Confirm that you want real exchange orders."}
        from pulsearb.engine.live_ready import assess_live_ready

        report = await assess_live_ready(
            self.config,
            killed=self.risk.killed,
            armed=False,
            venue=self.desk.live_venue,
        )
        if not report.get("ready"):
            return {
                "ok": False,
                "error": report.get("note") or "Live ready check did not pass.",
                "ready": False,
            }
        if not self._ensure_live_router():
            return {
                "ok": False,
                "                error": (
                    f"No {self.desk.live_venue.title()} key file. "
                    "Save the matching file in keys\\, then Check again."
                ),
            }
        self.live_armed = True
        if isinstance(self.broker, LiveRouter):
            self.broker.armed = True
            self.broker.live_venue = self.desk.live_venue
        self._apply_mode_settings()
        await self._refresh_cash()
        await self.broadcast()
        venue_label = self.desk.live_venue.title()
        return {
            "ok": True,
            "execution": "live",
            "desk": self.desk_view(),
            "note": (
                f"LIVE on {venue_label}. Same-exchange USD round-trips only. "
                "Each tap starts in USD and aims to finish in USD. Cross-exchange gaps stay paper."
            ),
        }

    async def _refresh_cash(self) -> None:
        broker = self._broker_for_live() if isinstance(self.broker, LiveRouter) else None
        if broker is None or not hasattr(broker, "refresh_balances"):
            return
        try:
            await broker.refresh_balances()
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
        usd_only = usd_spendable(balances)
        kill_paused = bool(self.risk.killed and live)
        fill_list = list(self.fills)[:80]
        if kill_paused:
            live_note = (
                "LIVE is still on. Kill switch paused new orders. Click Resume. You are not back on paper."
            )
        elif live:
            venue_label = self.desk.live_venue.title()
            if self.desk.live_venue in {"coinbase", "kraken"}:
                live_note = (
                    f"LIVE on {venue_label}: USD vs USDC books and same-exchange triangles. "
                    "Each tap buys with USD (market) and sells as a maker limit, then markets "
                    "anything still open after a few seconds so leftover coins do not sit. "
                    "Cross-venue stays paper. Each tap is your desk size. Session budget is the $25 cap."
                )
            elif self.desk.live_venue == "oanda":
                live_note = (
                    "LIVE on OANDA: one USD-quoted pair, open then close the same size. "
                    "Triangles stay paper. Leverage does not enlarge the tap."
                )
            else:
                live_note = (
                    f"LIVE on {venue_label}: same-exchange USD-start taps. "
                    "Buys and sells are market/IOC. Cross-venue stays paper. Session budget is the $25 cap."
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
                "usd_spendable": round(usd_only, 2),
                "live_note": live_note,
                "live_notional": self.desk.notional,
                "idle_reason": self._idle_reason(),
                "last_block": self.last_block,
            },
            "desk": self.desk_view(),
            "quotes": [q.to_dict() for q in quotes if self.desk.quote_ok(q, self.book)],
            "opportunities": [
                self._opp_view(o)
                for o in list(self.opportunities)[:40]
                if not any(leg.venue in SITE_HIDDEN_VENUES for leg in o.legs)
            ],
            "fills": [f.to_dict() for f in fill_list],
            "trades": group_trades(fill_list),
        }

    def clear_boards(self, *, opportunities: bool = True, fills: bool = True) -> dict:
        """Empty the on-screen tapes. Does not cancel live orders or move cash."""
        if opportunities:
            self.opportunities.clear()
            self.seen.clear()
            self.by_id.clear()
            self.stats.opportunities = 0
        if fills:
            self.fills.clear()
            self.invested.clear()
            self.paper.fills.clear()
            self.paper.pnl = 0.0
            broker = self.broker
            if getattr(broker, "fills", None) is not None and broker.fills is not self.paper.fills:
                broker.fills.clear()
            for name in ("coinbase", "kraken", "binance"):
                inner = getattr(broker, name, None)
                if inner is None:
                    continue
                fills_list = getattr(inner, "fills", None)
                if fills_list is not None and fills_list is not self.paper.fills:
                    fills_list.clear()
                if hasattr(inner, "pnl"):
                    inner.pnl = 0.0
            self.report.clear()
        return {
            "ok": True,
            "opportunities": bool(opportunities),
            "fills": bool(fills),
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
        live = self.live_active()
        auto_ok = auto_route_ok(opp, self.desk.live_venue, live=live)
        paper_only = bool(opp.executable) and not auto_ok
        can_click = (
            opp.executable
            and opp.id not in self.invested
            and self.desk.matches(opp, self.book)
            and not self.risk.killed
            and (auto_ok if live else True)
        )
        data.update(
            {
                "kind_label": KIND_LABELS.get(opp.kind.value, opp.kind.value),
                "expected_pnl": round(self.desk.notional * opp.net_edge_bps / 10_000, 4),
                "notional": self.desk.notional,
                "pending": can_click and auto_ok,
                "investable": can_click and not self.desk.auto_invest,
                "chosen": self.desk.matches(opp, self.book),
                "live_ok": auto_ok,
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
                "live_venues_ready": self.config.live_venue_names(),
                "last_block": self.last_block,
                "idle_reason": self._idle_reason(),
            }
        )
        return data

    def _set_last_block(self, note: str, *, source: str) -> None:
        text = str(note or "").strip()
        if not text:
            return
        self.last_block = {"note": text, "source": source, "ts": time.time()}

    def _live_rows(self) -> list[Opportunity]:
        return [
            opp
            for opp in self.opportunities
            if opp.executable
            and live_exec_ok(opp, self.desk.live_venue)
            and self.desk.matches(opp, self.book)
            and opp.id not in self.invested
        ]

    def _idle_reason(self) -> str:
        if not self.live_active():
            if self.desk.auto_invest and not self._auto_candidates(list(self.opportunities)):
                return (
                    "Auto only takes Coinbase or Kraken same-exchange rows that buy with USD. "
                    "Cross-venue gaps (Kraken vs Gemini) stay click-to-paper so they cannot starve those taps."
                )
            return ""
        venue = self.desk.live_venue.title()
        parts: list[str] = []
        if self.risk.killed:
            return "Kill switch paused new orders. Click Resume. You are still LIVE."
        bals = getattr(self.broker, "balances", {}) or {}
        usd = usd_spendable(bals)
        cash = quote_cash(bals)
        if bals and usd + 1e-9 < self.desk.notional:
            if cash + 1e-9 >= self.desk.notional:
                parts.append(
                    f"Live taps spend USD first. {venue} has ${usd:.2f} USD and "
                    f"${cash:.2f} including USDC/USDT. Move at least ${self.desk.notional:.0f} into USD."
                )
            else:
                parts.append(
                    f"Not enough USD on {venue} for a ${self.desk.notional:.0f} tap (USD ${usd:.2f})."
                )
        live_rows = self._live_rows()
        if self.desk.auto_invest:
            if not self.desk.schedule_enabled:
                parts.append("Auto is off while live unless you turn on Only between.")
            elif not self.desk.schedule_active():
                parts.append(f"Auto window is closed until {self.desk.schedule_start}.")
            elif not live_rows:
                parts.append(
                    f"Auto is on. No executable {venue} USD-start row this scan. "
                    f"Raising the tap to ${self.desk.notional:.0f} does not create a gap."
                )
            else:
                decision = self.risk.allow(self.desk.notional)
                if not decision.allowed:
                    parts.append(f"Auto saw a {venue} row but did not send it: {decision.reason}.")
        elif not live_rows:
            parts.append(
                f"No executable {venue} USD-start row right now. "
                f"A ${self.desk.notional:.0f} tap still needs a real same-exchange gap after fees."
            )
        if self.last_block:
            note = str(self.last_block.get("note") or "")
            if note and note not in " ".join(parts):
                parts.insert(0, f"Last tap blocked: {note}")
        return " ".join(parts)

    def apply_desk(self, payload: dict) -> dict:
        previous_venue = self.desk.live_venue
        self.desk.live = self.live_active()
        self.desk.apply(payload)
        if isinstance(self.broker, LiveRouter):
            self.broker.live_venue = self.desk.live_venue
        if self.live_active() and self.desk.live_venue != previous_venue:
            self._ensure_live_router()
        return self.desk_view()

    async def invest(self, opportunity_id: str) -> dict:
        opp = self.by_id.get(opportunity_id)
        if opp is None:
            error = "That trade is no longer on the board."
            self._set_last_block(error, source="invest")
            return {"ok": False, "error": error}
        if not opp.executable:
            error = "That row is watch-only (delayed data)."
            self._set_last_block(error, source="invest")
            return {"ok": False, "error": error}
        if not self.desk.matches(opp, self.book):
            error = "That pair is outside your price filter, or that coin/exchange is off."
            self._set_last_block(error, source="invest")
            return {"ok": False, "error": error}
        if opportunity_id in self.invested:
            error = "You already took this trade."
            self._set_last_block(error, source="invest")
            return {"ok": False, "error": error}
        if self.live_active() and not live_exec_ok(opp, self.desk.live_venue):
            venue_label = self.desk.live_venue.title()
            error = (
                f"Live only takes {venue_label} round-trips that buy with USD and sell back toward USD. "
                "Cross-exchange gaps stay paper."
            )
            self._set_last_block(error, source="invest")
            return {
                "ok": False,
                "error": error,
            }
        fills = await self._take(opp)
        await self.broadcast()
        if not any(item.status == "filled" for item in fills):
            note = next((item.note for item in fills if item.note), "Could not complete the buy and sell.")
            self._set_last_block(note, source="broker")
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
                if fill.note:
                    self._set_last_block(fill.note, source="auto" if self.desk.auto_invest else "broker")
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

    def _auto_candidates(self, current: list[Opportunity]) -> list[Opportunity]:
        live = self.live_active()
        return [
            opp
            for opp in current
            if opp.executable
            and self.desk.matches(opp, self.book)
            and auto_route_ok(opp, self.desk.live_venue, live=live)
        ]

    def _demo_instruments(self) -> list[tuple[str, str, bool]]:
        rows: list[tuple[str, str, bool]] = []
        for venue in SPOT_VENUES:
            if venue in SITE_HIDDEN_VENUES:
                continue
            if venue == "binance" and not self.config.env.enable_binance:
                continue
            for symbol in self.config.symbols(venue):
                try:
                    canon = canonical_from_pair(symbol)
                except ValueError:
                    continue
                rows.append((venue, canon, True))
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
            if self.config.venue_enabled("oanda"):
                oanda_creds = self.config.oanda_credentials()
                if oanda_creds:
                    account_id, access_token, environment = oanda_creds
                    cfg = markets["oanda"]
                    tasks.append(
                        OandaFeed(
                            symbols=self.config.symbols("oanda"),
                            account_id=account_id,
                            access_token=access_token,
                            environment=environment,
                            poll_seconds=float(cfg.get("poll_seconds") or settings.get("oanda_poll_seconds", 2.0)),
                        ).run(self.book, self.stats.feed_status)
                    )
                else:
                    self.stats.feed_status["oanda"] = "no keys\\oanda.json - skipped"
            if self.config.venue_enabled("robinhood"):
                robinhood_creds = self.config.robinhood_credentials()
                if robinhood_creds:
                    api_key, private_key = robinhood_creds
                    cfg = markets["robinhood"]
                    tasks.append(
                        RobinhoodFeed(
                            symbols=self.config.symbols("robinhood"),
                            api_key=api_key,
                            private_key_base64=private_key,
                            poll_seconds=float(cfg.get("poll_seconds") or settings.get("robinhood_poll_seconds", 1.0)),
                        ).run(self.book, self.stats.feed_status)
                    )
                else:
                    self.stats.feed_status["robinhood"] = "no keys\\robinhood.json - skipped"
        if not tasks:
            raise RuntimeError("No market feeds enabled")
        await asyncio.gather(*tasks)

    async def run_scanner(self) -> None:
        interval = self.config.scan_interval_ms / 1000.0
        fee_map = self._fee_map
        extra = self._slippage
        min_alert = float(self.config.settings.get("min_edge_bps", 8))
        min_exec = float(self.config.settings.get("min_executable_edge_bps", 15))
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
                maker = venue_maker_bps(fee_map, venue)
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
                        maker_bps=maker,
                    )
                )
            dislocations: list[Opportunity] = []
            for venue in ("coinbase", "kraken", "gemini"):
                dislocations.extend(
                    detect_quote_dislocations(
                        self.book,
                        venue=venue,
                        min_edge_bps=min_alert,
                        fee_map=fee_map,
                        extra_slippage_bps=extra,
                        notional=notional,
                        min_executable_edge_bps=min_exec,
                        max_raw_edge_bps=max_raw,
                        max_quote_age=stale,
                        max_quote_skew=max_skew,
                    )
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
            in_window = (not self.desk.schedule_enabled) or window_open(
                self.desk.schedule_start, self.desk.schedule_stop
            )
            want_auto = bool(self.desk.auto_invest) and not self.risk.killed and in_window
            if self.live_active() or self.desk.live:
                want_auto = want_auto and self.desk.schedule_enabled and in_window
            if want_auto and self.risk.allow(self.desk.notional).allowed:
                candidates = self._auto_candidates(current)
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
    broker = engine._broker_for_live() if isinstance(engine.broker, LiveRouter) else None
    if broker is not None and hasattr(broker, "refresh_balances"):
        balances = await broker.refresh_balances()
        engine._balances_at = time.time()
        shown = ", ".join(
            f"{asset} {amount:.6g}" for asset, amount in list(balances.items())[:8]
        ) or "(empty)"
        print(f"{PRODUCT} {engine.desk.live_venue} account: {shown}")
    await asyncio.gather(engine.run_feeds(), engine.run_scanner())
