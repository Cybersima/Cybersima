"""Forex desk: 3-second tape, multi-timeframe pattern recognition, entry/exit.

Paper trading is the default. Yahoo Finance is delayed retail data — useful for
timing and dislocation research, not a 1ms prime-broker pipe.
"""

from __future__ import annotations

import hashlib
import math
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from securetrade.engine.book import MarketBook
from securetrade.models import Leg, Opportunity, OpportunityKind, PaperOutcome, PaperPosition, Quote
from securetrade.symbols import split_pair


TIMEFRAMES: tuple[tuple[str, int], ...] = (
    ("30s", 30),
    ("1m", 60),
    ("2m", 120),
    ("3m", 180),
    ("4m", 240),
    ("5m", 300),
    ("1h", 3600),
    ("1d", 86400),
)

TIMEFRAME_SECONDS = {name: seconds for name, seconds in TIMEFRAMES}
FAST_TFS = ("30s", "1m", "2m", "3m")
SWING_TFS = ("4m", "5m", "1h", "1d")
HOLD_SECONDS = {
    "30s": 8 * 60,
    "1m": 20 * 60,
    "2m": 40 * 60,
    "3m": 60 * 60,
    "4m": 90 * 60,
    "5m": 2 * 60 * 60,
    "1h": 12 * 60 * 60,
    "1d": 5 * 24 * 60 * 60,
}
TF_STOP_MULT = {
    "30s": 0.55,
    "1m": 0.7,
    "2m": 0.85,
    "3m": 1.0,
    "4m": 1.1,
    "5m": 1.2,
    "1h": 1.8,
    "1d": 2.6,
}
MAX_BARS = {
    "30s": 480,
    "1m": 400,
    "2m": 360,
    "3m": 320,
    "4m": 300,
    "5m": 300,
    "1h": 240,
    "1d": 260,
}

# Synthetic majors used when Yahoo history is unavailable (demo / offline).
FX_SEEDS: dict[str, float] = {
    "EUR-USD": 1.0854,
    "GBP-USD": 1.2748,
    "USD-JPY": 149.22,
    "AUD-USD": 0.6621,
    "USD-CAD": 1.3852,
    "USD-CHF": 0.8684,
    "NZD-USD": 0.5983,
    "EUR-GBP": 0.8512,
    "EUR-JPY": 161.94,
    "GBP-JPY": 190.18,
    "EUR-CHF": 0.9421,
    "AUD-JPY": 98.82,
    "USD-CNH": 7.241,
    "USD-SEK": 10.552,
    "USD-NOK": 10.718,
    "USD-MXN": 18.452,
    "EUR-AUD": 1.6392,
    "EUR-CAD": 1.5034,
    "GBP-AUD": 1.9256,
    "GBP-CHF": 1.1071,
    "AUD-NZD": 1.1066,
    "NZD-JPY": 89.28,
    "CAD-JPY": 107.72,
    "CHF-JPY": 171.82,
    "EUR-NZD": 1.8141,
    "USD-ZAR": 18.21,
    "USD-TRY": 32.45,
    "GBP-CAD": 1.7658,
    "AUD-CAD": 0.9172,
    "EUR-SEK": 11.452,
}


@dataclass(slots=True)
class Candle:
    start: float
    open: float
    high: float
    low: float
    close: float
    volume: float = 1.0


@dataclass
class TimeframeBias:
    timeframe: str
    bias: str
    rsi: float
    ema_fast: float
    ema_slow: float
    macd_hist: float
    momentum_bps: float
    pattern: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ForexSignal:
    pair: str
    side: str
    timeframe: str
    pattern: str
    confluence: int
    aligned: list[str]
    entry: float
    stop: float
    target: float
    edge_bps: float
    ts: float
    why: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ForexPosition:
    opportunity_id: str
    pair: str
    side: str
    timeframe: str
    pattern: str
    entry: float
    stop: float
    target: float
    notional: float
    opened_at: float
    last_price: float = 0.0
    trail: float = 0.0
    unrealized_pnl: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ForexExit:
    opportunity_id: str
    pair: str
    side: str
    price: float
    pnl: float
    outcome: PaperOutcome
    reason: str
    ts: float


def ema(values: list[float], period: int) -> float | None:
    if period <= 0 or len(values) < period:
        return None
    k = 2.0 / (period + 1)
    current = sum(values[:period]) / period
    for price in values[period:]:
        current = price * k + current * (1.0 - k)
    return current


def rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
    for prev, price in zip(values[-(period + 1) : -1], values[-period:]):
        delta = price - prev
        if delta >= 0:
            gains += delta
        else:
            losses -= delta
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def macd_hist(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> float | None:
    if len(values) < slow + signal:
        return None
    macd_line: list[float] = []
    for idx in range(slow, len(values) + 1):
        window = values[:idx]
        fast_ema = ema(window, fast)
        slow_ema = ema(window, slow)
        if fast_ema is None or slow_ema is None:
            continue
        macd_line.append(fast_ema - slow_ema)
    if len(macd_line) < signal:
        return None
    signal_line = ema(macd_line, signal)
    if signal_line is None:
        return None
    return macd_line[-1] - signal_line


def atr(candles: list[Candle], period: int = 14) -> float | None:
    if len(candles) < period + 1:
        return None
    ranges: list[float] = []
    for prev, candle in zip(candles[-(period + 1) : -1], candles[-period:]):
        ranges.append(max(candle.high - candle.low, abs(candle.high - prev.close), abs(candle.low - prev.close)))
    if not ranges:
        return None
    return sum(ranges) / len(ranges)


def momentum_bps(values: list[float], lookback: int) -> float:
    if len(values) <= lookback or values[-lookback - 1] == 0:
        return 0.0
    start = values[-lookback - 1]
    return (values[-1] - start) / start * 10_000


def _oid(*parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


class ForexDesk:
    """Scans FX pairs, times entries, and exits before the move decays."""

    def __init__(
        self,
        *,
        min_confluence: int = 3,
        notional: float = 250.0,
        max_open: int = 6,
        cooldown_seconds: float = 45.0,
        min_edge_bps: float = 8.0,
        poll_seconds: float = 3.0,
    ) -> None:
        self.min_confluence = min_confluence
        self.notional = notional
        self.max_open = max_open
        self.cooldown_seconds = cooldown_seconds
        self.min_edge_bps = min_edge_bps
        self.poll_seconds = poll_seconds
        self.candles: dict[str, dict[str, deque[Candle]]] = defaultdict(
            lambda: {name: deque(maxlen=MAX_BARS[name]) for name, _seconds in TIMEFRAMES}
        )
        self.ticks: dict[str, deque[tuple[float, float]]] = defaultdict(lambda: deque(maxlen=240))
        self.last_ts: dict[str, float] = {}
        self.last_price: dict[str, float] = {}
        self.positions: dict[str, ForexPosition] = {}
        self.signals: deque[ForexSignal] = deque(maxlen=80)
        self.exits: deque[dict[str, Any]] = deque(maxlen=80)
        self.cooldowns: dict[str, float] = {}
        self.seen: set[str] = set()
        self.entries = 0
        self.closed_wins = 0
        self.closed_losses = 0
        self.seeded = False

    def observe_quote(self, quote: Quote) -> None:
        if quote.asset_class not in {"fx", "metal"} and not _looks_fx(quote.canonical):
            return
        mid = quote.mid
        if mid <= 0:
            return
        self.ingest_tick(quote.canonical, quote.ts, mid)

    def observe_book(self, book: MarketBook) -> None:
        for quote in book.snapshot():
            self.observe_quote(quote)

    def ingest_tick(self, pair: str, ts: float, price: float) -> None:
        pair = pair.upper()
        if price <= 0:
            return
        prev = self.last_ts.get(pair)
        if prev is not None and ts < prev:
            return
        self.last_ts[pair] = ts
        self.last_price[pair] = price
        self.ticks[pair].append((ts, price))
        for name, seconds in TIMEFRAMES:
            bucket = math.floor(ts / seconds) * seconds
            series = self.candles[pair][name]
            if series and series[-1].start == bucket:
                candle = series[-1]
                candle.high = max(candle.high, price)
                candle.low = min(candle.low, price)
                candle.close = price
                candle.volume += 1.0
            else:
                series.append(Candle(start=bucket, open=price, high=price, low=price, close=price))

    def seed_synthetic(self, pairs: Iterable[str], *, now: float | None = None, bars: int = 220) -> None:
        now = now or time.time()
        for pair in pairs:
            pair = pair.upper()
            price = FX_SEEDS.get(pair, self.last_price.get(pair, 1.0))
            step = TIMEFRAME_SECONDS["30s"]
            start = now - bars * step
            drift = 0.00004 if hash(pair) % 2 == 0 else -0.00004
            current = price * (1.0 - drift * bars / 2)
            for idx in range(bars):
                ts = start + idx * step
                wave = math.sin(idx / 18.0) * 0.00035
                current = max(current * (1.0 + drift + wave), 1e-8)
                self.ingest_tick(pair, ts, current)
            self.ingest_tick(pair, now, price)
        self.seeded = True

    def seed_from_closes(self, pair: str, closes: list[tuple[float, float]]) -> None:
        for ts, price in closes:
            self.ingest_tick(pair.upper(), ts, price)
        self.seeded = True

    def biases(self, pair: str) -> list[TimeframeBias]:
        pair = pair.upper()
        rows: list[TimeframeBias] = []
        for name, _seconds in TIMEFRAMES:
            candles = list(self.candles[pair][name])
            closes = [c.close for c in candles]
            if len(closes) < 8:
                rows.append(TimeframeBias(name, "flat", 50.0, 0.0, 0.0, 0.0, 0.0, "warming up"))
                continue
            fast = ema(closes, 9) or closes[-1]
            slow = ema(closes, 21) or closes[0]
            rsi_val = rsi(closes) or 50.0
            hist = macd_hist(closes) or 0.0
            mom = momentum_bps(closes, min(8, len(closes) - 1))
            pattern = _pattern(closes, candles, fast, slow, rsi_val, hist, mom)
            if fast > slow and mom > 0:
                bias = "up"
            elif fast < slow and mom < 0:
                bias = "down"
            elif mom > 4:
                bias = "up"
            elif mom < -4:
                bias = "down"
            else:
                bias = "flat"
            rows.append(
                TimeframeBias(
                    timeframe=name,
                    bias=bias,
                    rsi=round(rsi_val, 2),
                    ema_fast=fast,
                    ema_slow=slow,
                    macd_hist=hist,
                    momentum_bps=round(mom, 2),
                    pattern=pattern,
                )
            )
        return rows

    def snapshot_pairs(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for pair, price in sorted(self.last_price.items()):
            ticks = list(self.ticks[pair])
            change = 0.0
            if len(ticks) >= 2 and ticks[0][1]:
                change = (ticks[-1][1] - ticks[0][1]) / ticks[0][1] * 10_000
            biases = self.biases(pair)
            up = [b.timeframe for b in biases if b.bias == "up"]
            down = [b.timeframe for b in biases if b.bias == "down"]
            if len(up) > len(down) and len(up) >= 2:
                signal = "BUY"
            elif len(down) > len(up) and len(down) >= 2:
                signal = "SELL"
            else:
                signal = "HOLD"
            spark = [round(p, 8) for _ts, p in ticks[-40:]]
            rows.append(
                {
                    "pair": pair.replace("-", "/"),
                    "canonical": pair,
                    "last": price,
                    "change_bps": round(change, 2),
                    "signal": signal,
                    "confluence": max(len(up), len(down)),
                    "aligned": up if signal == "BUY" else down if signal == "SELL" else [],
                    "timeframes": [b.to_dict() for b in biases],
                    "spark": spark,
                    "open": pair in {p.pair for p in self.positions.values()},
                }
            )
        return rows

    def scan(self, book: MarketBook, now: float | None = None) -> list[Opportunity]:
        now = now or time.time()
        self.observe_book(book)
        found: list[Opportunity] = []
        found.extend(self._directional(book, now))
        found.extend(self._triangles(book, now))
        return found

    def adopt(self, opportunity: Opportunity) -> ForexPosition | None:
        if not _is_forex(opportunity) or opportunity.id in self.positions:
            return None
        if len(self.positions) >= self.max_open:
            return None
        pos = ForexPosition(
            opportunity_id=opportunity.id,
            pair=(opportunity.pair or "").replace("/", "-").upper(),
            side=opportunity.side or "buy",
            timeframe=opportunity.timeframe or "5m",
            pattern=opportunity.pattern,
            entry=opportunity.entry_price,
            stop=opportunity.stop_price,
            target=opportunity.target_price,
            notional=opportunity.notional,
            opened_at=opportunity.ts or time.time(),
            last_price=opportunity.entry_price,
            trail=opportunity.stop_price,
        )
        self.positions[opportunity.id] = pos
        self.cooldowns[pos.pair] = time.time() + self.cooldown_seconds
        self.entries += 1
        return pos

    def mark(self, book: MarketBook, now: float | None = None) -> list[ForexExit]:
        now = now or time.time()
        self.observe_book(book)
        closed: list[ForexExit] = []
        for oid, pos in list(self.positions.items()):
            price = self._mark_price(pos.pair, book)
            if price <= 0:
                continue
            pos.last_price = price
            pos.unrealized_pnl = _pnl(pos.side, pos.entry, price, pos.notional)
            self._trail(pos, price)
            exit_reason = self._should_exit(pos, price, now)
            if not exit_reason:
                continue
            pnl = _pnl(pos.side, pos.entry, price, pos.notional)
            if exit_reason == "take-profit" or pnl > 0:
                outcome = PaperOutcome.CAPTURED
                self.closed_wins += 1
            elif exit_reason == "stop-loss" or pnl < 0:
                outcome = PaperOutcome.REVERSED
                self.closed_losses += 1
            else:
                outcome = PaperOutcome.EXPIRED if pnl == 0 else PaperOutcome.CAPTURED
                if pnl >= 0:
                    self.closed_wins += 1
                else:
                    self.closed_losses += 1
            closed.append(
                ForexExit(
                    opportunity_id=oid,
                    pair=pos.pair,
                    side=pos.side,
                    price=price,
                    pnl=pnl,
                    outcome=outcome,
                    reason=exit_reason,
                    ts=now,
                )
            )
            self.exits.appendleft(
                {
                    "opportunity_id": oid,
                    "pair": pos.pair.replace("-", "/"),
                    "side": pos.side,
                    "price": price,
                    "pnl": round(pnl, 4),
                    "outcome": outcome.value,
                    "reason": exit_reason,
                    "ts": now,
                }
            )
            self.positions.pop(oid, None)
            self.cooldowns[pos.pair] = now + self.cooldown_seconds
        return closed

    def flatten(self, book: MarketBook, now: float | None = None) -> list[ForexExit]:
        now = now or time.time()
        for pos in self.positions.values():
            pos.trail = pos.last_price or pos.entry
            # Force time-stop path via a past open time.
            pos.opened_at = now - HOLD_SECONDS.get(pos.timeframe, 60) - 1
        return self.mark(book, now)

    def to_snapshot(self) -> dict[str, Any]:
        closed = self.closed_wins + self.closed_losses
        win_rate = (self.closed_wins / closed * 100) if closed else 0.0
        return {
            "timeframes": [name for name, _seconds in TIMEFRAMES],
            "poll_seconds": self.poll_seconds,
            "feed": "yahoo",
            "pairs": self.snapshot_pairs(),
            "signals": [s.to_dict() for s in list(self.signals)[:40]],
            "positions": [p.to_dict() for p in self.positions.values()],
            "exits": list(self.exits)[:40],
            "stats": {
                "pairs": len(self.last_price),
                "open": len(self.positions),
                "entries": self.entries,
                "wins": self.closed_wins,
                "losses": self.closed_losses,
                "win_rate": round(win_rate, 1),
                "seeded": self.seeded,
            },
        }

    def _directional(self, book: MarketBook, now: float) -> list[Opportunity]:
        if len(self.positions) >= self.max_open:
            return []
        found: list[Opportunity] = []
        for pair, price in self.last_price.items():
            if pair in {p.pair for p in self.positions.values()}:
                continue
            if self.cooldowns.get(pair, 0) > now:
                continue
            quote = _fx_quote(book, pair)
            if quote is None:
                continue
            biases = self.biases(pair)
            up = [b for b in biases if b.bias == "up"]
            down = [b for b in biases if b.bias == "down"]
            if len(up) >= self.min_confluence and len(up) > len(down):
                side = "buy"
                aligned = up
            elif len(down) >= self.min_confluence and len(down) > len(up):
                side = "sell"
                aligned = down
            else:
                continue
            fast_ok = sum(1 for b in aligned if b.timeframe in FAST_TFS)
            if fast_ok < 1:
                continue
            trigger = next((b for b in aligned if b.pattern not in {"", "warming up", "quiet"}), aligned[0])
            if trigger.pattern in {"warming up", "quiet"} and len(aligned) < self.min_confluence + 1:
                continue
            timing = next((b.timeframe for b in aligned if b.timeframe in FAST_TFS), trigger.timeframe)
            stop, target, edge = self._levels(pair, price, side, timing)
            if edge < self.min_edge_bps:
                continue
            oid = _oid("fx", pair, side, timing, int(now // 30))
            if oid in self.seen:
                continue
            self.seen.add(oid)
            why = [
                f"{len(aligned)}/{len(TIMEFRAMES)} timeframes aligned {side.upper()}",
                f"Pattern: {trigger.pattern}",
                f"Timing on {timing} · Yahoo tape every {self.poll_seconds:.0f}s",
                f"Stop {stop:.6g} · target {target:.6g} · {edge:.1f} bps edge",
            ]
            signal = ForexSignal(
                pair=pair.replace("-", "/"),
                side=side,
                timeframe=timing,
                pattern=trigger.pattern,
                confluence=len(aligned),
                aligned=[b.timeframe for b in aligned],
                entry=price,
                stop=stop,
                target=target,
                edge_bps=edge,
                ts=now,
                why=why,
            )
            self.signals.appendleft(signal)
            found.append(
                Opportunity(
                    kind=OpportunityKind.FOREX_DIRECTIONAL,
                    edge_bps=edge,
                    net_edge_bps=edge,
                    notional=self.notional,
                    legs=[
                        Leg(
                            action=side,
                            venue=quote.venue,
                            symbol=quote.native_symbol,
                            price=price,
                            executable=quote.executable,
                            size=quote.ask_size or quote.bid_size,
                        )
                    ],
                    summary=f"{side.upper()} {pair.replace('-', '/')} on {timing} · {trigger.pattern}",
                    executable=quote.executable,
                    ts=now,
                    id=oid,
                    pair=pair.replace("-", "/"),
                    liquidity_usd=max(self.notional * 40, 50_000),
                    execution_confidence=min(0.84, 0.52 + 0.04 * len(aligned)),
                    side=side,
                    timeframe=timing,
                    entry_price=price,
                    stop_price=stop,
                    target_price=target,
                    pattern=trigger.pattern,
                    confluence=len(aligned),
                    timeframes_aligned=[b.timeframe for b in aligned],
                    why=why,
                )
            )
        return found

    def _triangles(self, book: MarketBook, now: float) -> list[Opportunity]:
        routes = (
            ("EUR-USD", "USD-JPY", "EUR-JPY", False),
            ("EUR-USD", "GBP-USD", "EUR-GBP", True),
            ("GBP-USD", "USD-JPY", "GBP-JPY", False),
            ("AUD-USD", "USD-JPY", "AUD-JPY", False),
            ("EUR-USD", "USD-CHF", "EUR-CHF", False),
            ("EUR-USD", "AUD-USD", "EUR-AUD", True),
        )
        found: list[Opportunity] = []
        for left, right, implied, divide in routes:
            a = self.last_price.get(left)
            b = self.last_price.get(right)
            c = self.last_price.get(implied)
            if not a or not b or not c:
                continue
            synthetic = (a / b) if divide else (a * b)
            if synthetic <= 0:
                continue
            dislocation = abs(synthetic - c) / c * 10_000
            if dislocation < max(self.min_edge_bps, 6.0):
                continue
            oid = _oid("fxarb", implied, int(now // 6))
            if oid in self.seen:
                continue
            self.seen.add(oid)
            quote = _fx_quote(book, implied) or _fx_quote(book, left)
            if quote is None:
                continue
            side = "sell" if synthetic > c else "buy"
            why = [
                f"Forex triangle dislocation {dislocation:.1f} bps",
                f"{left} × {right} implies {implied} {synthetic:.6g} vs tape {c:.6g}",
                "Window is measured on the 3-second Yahoo tape",
            ]
            found.append(
                Opportunity(
                    kind=OpportunityKind.FOREX_ARBITRAGE,
                    edge_bps=dislocation,
                    net_edge_bps=dislocation,
                    notional=self.notional,
                    legs=[
                        Leg("buy" if not divide else "sell", quote.venue, left, a, quote.executable),
                        Leg("buy", quote.venue, right, b, quote.executable),
                        Leg(side, quote.venue, implied, c, quote.executable),
                    ],
                    summary=f"FX arb {implied.replace('-', '/')} {dislocation:.1f} bps vs {left}/{right}",
                    executable=False,
                    ts=now,
                    id=oid,
                    pair=implied.replace("-", "/"),
                    liquidity_usd=80_000,
                    execution_confidence=0.58,
                    side=side,
                    timeframe="30s",
                    entry_price=c,
                    stop_price=c * (0.999 if side == "buy" else 1.001),
                    target_price=synthetic,
                    pattern="triangle dislocation",
                    confluence=3,
                    timeframes_aligned=["30s", "1m"],
                    why=why,
                )
            )
        return found

    def _levels(self, pair: str, price: float, side: str, timeframe: str) -> tuple[float, float, float]:
        candles = list(self.candles[pair][timeframe])
        raw_atr = atr(candles) or price * 0.0006
        mult = TF_STOP_MULT.get(timeframe, 1.0)
        stop_dist = max(raw_atr * mult, price * 0.0008)
        target_dist = stop_dist * 1.6
        if side == "buy":
            stop = price - stop_dist
            target = price + target_dist
        else:
            stop = price + stop_dist
            target = price - target_dist
        edge = target_dist / price * 10_000
        return stop, target, edge

    def _should_exit(self, pos: ForexPosition, price: float, now: float) -> str:
        if pos.side == "buy":
            if price >= pos.target:
                return "take-profit"
            if price <= pos.trail or price <= pos.stop:
                return "stop-loss"
        else:
            if price <= pos.target:
                return "take-profit"
            if price >= pos.trail or price >= pos.stop:
                return "stop-loss"
        hold = HOLD_SECONDS.get(pos.timeframe, 3600)
        if now - pos.opened_at >= hold:
            return "time-stop"
        biases = self.biases(pos.pair)
        opposite = "down" if pos.side == "buy" else "up"
        fast_flip = sum(1 for b in biases if b.timeframe in FAST_TFS and b.bias == opposite)
        if fast_flip >= 3:
            return "pattern-reversal"
        return ""

    def _trail(self, pos: ForexPosition, price: float) -> None:
        risk = abs(pos.entry - pos.stop)
        if risk <= 0:
            return
        if pos.side == "buy":
            if price >= pos.entry + risk * 0.6:
                pos.trail = max(pos.trail, pos.entry)
            if price >= pos.entry + risk:
                pos.trail = max(pos.trail, price - risk * 0.6)
        else:
            if price <= pos.entry - risk * 0.6:
                pos.trail = min(pos.trail or pos.stop, pos.entry)
            if price <= pos.entry - risk:
                ceiling = pos.trail if pos.trail else pos.stop
                pos.trail = min(ceiling, price + risk * 0.6)

    def _mark_price(self, pair: str, book: MarketBook) -> float:
        quote = _fx_quote(book, pair)
        if quote:
            return quote.mid
        return self.last_price.get(pair, 0.0)


def attach_forex_levels(position: PaperPosition, opportunity: Opportunity) -> PaperPosition:
    position.side = opportunity.side
    position.entry_price = opportunity.entry_price
    position.stop_price = opportunity.stop_price
    position.target_price = opportunity.target_price
    position.timeframe = opportunity.timeframe
    position.asset_class = "fx"
    position.timeout_seconds = 0.0
    position.last_price = opportunity.entry_price
    return position


def _fx_quote(book: MarketBook, pair: str) -> Quote | None:
    quotes = book.by_canonical(pair)
    if not quotes:
        try:
            base, quote = split_pair(pair)
            found = book.find_pair(base, quote)
            if found:
                return found
        except ValueError:
            return None
        return None
    quotes = sorted(quotes, key=lambda q: (0 if q.venue == "yahoo" else 1, -q.ts))
    return quotes[0]


def _looks_fx(canonical: str) -> bool:
    try:
        base, quote = split_pair(canonical)
    except ValueError:
        return False
    fiat = {
        "USD",
        "EUR",
        "GBP",
        "JPY",
        "AUD",
        "CAD",
        "CHF",
        "NZD",
        "CNH",
        "SEK",
        "NOK",
        "MXN",
        "ZAR",
        "TRY",
        "XAU",
        "XAG",
    }
    crypto = {"BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "LTC", "USDT", "USDC"}
    return base in fiat and quote in fiat and base not in crypto and quote not in crypto


def _is_forex(opportunity: Opportunity) -> bool:
    kind = opportunity.kind.value if isinstance(opportunity.kind, OpportunityKind) else str(opportunity.kind)
    return kind in {OpportunityKind.FOREX_DIRECTIONAL.value, OpportunityKind.FOREX_ARBITRAGE.value}


def _pattern(
    closes: list[float],
    candles: list[Candle],
    fast: float,
    slow: float,
    rsi_val: float,
    hist: float,
    mom: float,
) -> str:
    if len(closes) < 6:
        return "warming up"
    prev_fast = ema(closes[:-1], 9) or fast
    prev_slow = ema(closes[:-1], 21) or slow
    highs = [c.high for c in candles[-21:-1]] if len(candles) > 21 else [c.high for c in candles[:-1]]
    lows = [c.low for c in candles[-21:-1]] if len(candles) > 21 else [c.low for c in candles[:-1]]
    if highs and closes[-1] > max(highs):
        return "range breakout"
    if lows and closes[-1] < min(lows):
        return "breakdown"
    if prev_fast <= prev_slow and fast > slow:
        return "EMA crossover"
    if prev_fast >= prev_slow and fast < slow:
        return "EMA death cross"
    if rsi_val < 32 and mom > 0:
        return "RSI reversal up"
    if rsi_val > 68 and mom < 0:
        return "RSI reversal down"
    if hist > 0 and mom > 6:
        return "MACD momentum"
    if hist < 0 and mom < -6:
        return "MACD fade"
    if abs(mom) > 12:
        return "impulse burst"
    if abs(mom) < 2 and 45 < rsi_val < 55:
        return "quiet"
    return "trend continuation"


def _pnl(side: str, entry: float, price: float, notional: float) -> float:
    if entry <= 0:
        return 0.0
    move = (price - entry) / entry if side == "buy" else (entry - price) / entry
    return notional * move


def is_forex_kind(kind: OpportunityKind | str) -> bool:
    value = kind.value if isinstance(kind, OpportunityKind) else str(kind)
    return value in {
        OpportunityKind.FOREX_DIRECTIONAL.value,
        OpportunityKind.FOREX_ARBITRAGE.value,
    }
