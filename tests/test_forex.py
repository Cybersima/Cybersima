import time

from securetrade.config import AppConfig
from securetrade.engine.book import MarketBook
from securetrade.engine.forex import ForexDesk, ForexPosition, ema, is_forex_kind, rsi
from securetrade.engine.paper_lab import PaperLab
from securetrade.engine.recovery_commit import RecoveryCommit
from securetrade.engine.runner import Engine
from securetrade.engine.simulate import SimulationResult
from securetrade.models import CommitDecision, Leg, Opportunity, OpportunityKind, Quote


def _quote(pair: str, price: float, ts: float | None = None) -> Quote:
    width = price * 0.00012
    return Quote(
        venue="yahoo",
        native_symbol=pair,
        canonical=pair,
        bid=price - width,
        ask=price + width,
        ts=ts or time.time(),
        asset_class="fx",
        executable=False,
        bid_size=1_000_000,
        ask_size=1_000_000,
    )


def _trend(pair: str, start: float, step: float, bars: int = 220, now: float = 1_700_000_000.0) -> list[tuple[float, float]]:
    return [(now - (bars - i) * 30, start + i * step) for i in range(bars)]


def test_indicators_and_timeframes() -> None:
    assert ema([1, 2, 3, 4, 5, 6, 7, 8, 9], 3) is not None
    assert rsi([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]) > 50
    desk = ForexDesk(min_confluence=3)
    now = 1_700_000_000.0
    for i in range(80):
        desk.ingest_tick("EUR-USD", now + i * 30, 1.08 + i * 0.0002)
    names = {name for name, _s in desk.candles["EUR-USD"].items() if desk.candles["EUR-USD"][name]}
    assert {"30s", "1m", "2m", "3m", "4m", "5m"}.issubset(names)
    assert desk.candles["EUR-USD"]["1m"][-1].close > desk.candles["EUR-USD"]["1m"][0].open


def test_buy_rising_and_sell_falling() -> None:
    now = 1_700_000_000.0
    book = MarketBook()
    up = ForexDesk(min_confluence=3, min_edge_bps=8)
    up.seed_from_closes("EUR-USD", _trend("EUR-USD", 1.05, 0.00035, now=now))
    book.update(_quote("EUR-USD", up.last_price["EUR-USD"], now))
    buys = [o for o in up.scan(book, now=now) if o.side == "buy"]
    assert buys
    assert buys[0].stop_price < buys[0].entry_price < buys[0].target_price
    assert is_forex_kind(buys[0].kind)
    assert buys[0].confluence >= 3

    down_book = MarketBook()
    down = ForexDesk(min_confluence=3, min_edge_bps=8)
    down.seed_from_closes("GBP-USD", _trend("GBP-USD", 1.32, -0.00035, now=now))
    down_book.update(_quote("GBP-USD", down.last_price["GBP-USD"], now))
    sells = [o for o in down.scan(down_book, now=now) if o.side == "sell"]
    assert sells
    assert sells[0].target_price < sells[0].entry_price < sells[0].stop_price


def test_exit_take_profit_and_stop() -> None:
    desk = ForexDesk()
    book = MarketBook()
    desk.positions["tp"] = ForexPosition(
        opportunity_id="tp",
        pair="EUR-USD",
        side="buy",
        timeframe="1m",
        pattern="EMA crossover",
        entry=1.10,
        stop=1.098,
        target=1.103,
        notional=250,
        opened_at=time.time(),
        last_price=1.10,
        trail=1.098,
    )
    book.update(_quote("EUR-USD", 1.104))
    exits = desk.mark(book)
    assert exits and exits[0].reason == "take-profit"
    assert exits[0].pnl > 0

    desk.positions["sl"] = ForexPosition(
        opportunity_id="sl",
        pair="USD-JPY",
        side="sell",
        timeframe="5m",
        pattern="breakdown",
        entry=149.0,
        stop=149.4,
        target=148.4,
        notional=250,
        opened_at=time.time(),
        last_price=149.0,
        trail=149.4,
    )
    book.update(_quote("USD-JPY", 149.5))
    exits = desk.mark(book)
    assert exits and exits[0].reason == "stop-loss"
    assert exits[0].pnl < 0


def test_forex_triangle_dislocation() -> None:
    desk = ForexDesk(min_edge_bps=8)
    now = time.time()
    desk.last_price.update({"EUR-USD": 1.10, "USD-JPY": 150.0, "EUR-JPY": 163.0})
    desk.last_ts.update({k: now for k in desk.last_price})
    book = MarketBook()
    book.update(_quote("EUR-JPY", 163.0, now))
    book.update(_quote("EUR-USD", 1.10, now))
    book.update(_quote("USD-JPY", 150.0, now))
    opps = desk._triangles(book, now)
    assert opps
    assert is_forex_kind(opps[0].kind)
    assert opps[0].edge_bps > 8


def test_paper_lab_holds_forex_until_exit() -> None:
    lab = PaperLab(timeout_seconds=0.01)
    pos = lab.open_from_opportunity(
        "fx1",
        "EUR/USD",
        250,
        2.0,
        "RESEARCH_COMMIT",
        12,
        80,
        now=time.time() - 5,
        timeout_seconds=0.0,
        side="buy",
        asset_class="fx",
    )
    assert pos is not None
    assert lab.expire_open() == []
    assert "fx1" in lab.open


def test_recovery_commit_allows_yahoo_age() -> None:
    gate = RecoveryCommit()
    opp = Opportunity(
        kind=OpportunityKind.FOREX_DIRECTIONAL,
        edge_bps=18,
        net_edge_bps=16,
        notional=250,
        legs=[Leg("buy", "yahoo", "EUR-USD", 1.08, False)],
        summary="BUY EUR/USD",
        executable=False,
        ts=time.time(),
        id="fx-age",
        pair="EUR/USD",
        execution_confidence=0.7,
        side="buy",
        timeframe="1m",
    )
    sim = SimulationResult(True, 250, 1.0, 15.0, [])
    rec = gate.evaluate(opp, sim, 4000, 4000, 200, 16)
    assert rec.decision in {CommitDecision.COMMIT.value, CommitDecision.RESEARCH_COMMIT.value}


def test_yahoo_poll_is_three_seconds() -> None:
    config = AppConfig()
    assert config.yahoo_poll_seconds == 3.0
    fx = [row for row in config.yahoo_symbols if row.get("asset_class") == "fx"]
    assert len(fx) >= 20
    assert config.forex.get("enabled", True)


def test_engine_snapshot_includes_forex_desk() -> None:
    config = AppConfig()
    config.env.demo_only = True
    config._apply_env_overrides()
    engine = Engine(config)
    snap = engine.snapshot()
    assert "forex" in snap
    assert snap["forex"]["poll_seconds"] == 3.0
    assert "30s" in snap["forex"]["timeframes"]
    assert "1d" in snap["forex"]["timeframes"]
    assert snap["forex"]["stats"]["pairs"] >= 10
