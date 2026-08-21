import pytest

from pulsearb.config import AppConfig
from pulsearb.engine.book import MarketBook
from pulsearb.engine.desk import TradeDesk, opportunity_assets
from pulsearb.engine.runner import Engine
from pulsearb.models import Leg, Opportunity, OpportunityKind, Quote


def _opp(kind: OpportunityKind = OpportunityKind.CROSS_VENUE, venues=("coinbase", "kraken"), symbol="BTC-USD") -> Opportunity:
    return Opportunity(
        kind=kind,
        edge_bps=40,
        net_edge_bps=28,
        notional=250,
        legs=[
            Leg("buy", venues[0], symbol, 100, True),
            Leg("sell", venues[1], symbol, 101, True),
        ],
        summary="test",
        executable=kind != OpportunityKind.ALERT,
        ts=0,
        id="desk-1",
    )


def _quote(venue: str, symbol: str, mid: float) -> Quote:
    return Quote(
        venue=venue,
        native_symbol=symbol,
        canonical=symbol,
        bid=mid * 0.999,
        ask=mid * 1.001,
        ts=1,
        executable=True,
    )


def _book(*rows: tuple[str, str, float]) -> MarketBook:
    book = MarketBook()
    for venue, symbol, mid in rows:
        book.update(_quote(venue, symbol, mid))
    return book


def test_desk_defaults_are_pick_mode_and_popular_coins() -> None:
    desk = TradeDesk()
    assert desk.auto_invest is False
    assert desk.notional == 5
    assert "BTC" in desk.assets
    assert desk.matches(_opp())


def test_notional_allows_one_dollar_taps() -> None:
    desk = TradeDesk(live=True, live_max=25, min_notional=1)
    desk.apply({"notional": 1})
    assert desk.notional == 1
    desk.apply({"notional": 0.25})
    assert desk.notional == 1
    assert 1 in desk.presets()
    assert 5 in desk.presets()


def test_notional_clamps_to_cap() -> None:
    desk = TradeDesk(live=True, live_max=25, max_notional=250)
    desk.apply({"notional": 500})
    assert desk.notional == 25


def test_desk_hides_unselected_coin() -> None:
    desk = TradeDesk(assets=["ETH"])
    assert not desk.matches(_opp(symbol="BTC-USD"))
    assert desk.matches(_opp(symbol="ETH-USD"))


def test_desk_can_exclude_an_exchange() -> None:
    desk = TradeDesk(venues=["coinbase"])
    assert not desk.matches(_opp(venues=("coinbase", "kraken")))
    triangle = _opp(kind=OpportunityKind.TRIANGULAR, venues=("coinbase", "coinbase"), symbol="ETH-BTC")
    assert desk.matches(triangle)


def test_auto_forced_off_when_live() -> None:
    desk = TradeDesk(live=True, live_max=25)
    desk.apply({"auto_invest": True})
    assert desk.auto_invest is False
    assert desk.to_dict()["auto_allowed"] is False


def test_auto_allowed_when_paper() -> None:
    desk = TradeDesk(live=False)
    desk.apply({"auto_invest": True})
    assert desk.auto_invest is True
    assert desk.to_dict()["auto_allowed"] is True


def test_opportunity_assets_skips_quote() -> None:
    assert opportunity_assets(_opp()) == {"BTC"}


@pytest.mark.asyncio
async def test_invest_uses_customer_amount() -> None:
    engine = Engine(AppConfig())
    engine.desk.notional = 15
    opp = _opp()
    engine.by_id[opp.id] = opp
    result = await engine.invest(opp.id)
    assert result["ok"] is True
    assert engine.paper.pnl != 0
    assert any(abs(fill.notional - 15) < 1e-9 for fill in engine.fills)


def test_under_filter_hides_expensive_pairs() -> None:
    desk = TradeDesk(assets=["BTC", "DOGE"])
    desk.apply({"price_mode": "under", "price_limit": 5})
    book = _book(
        ("coinbase", "BTC-USD", 100_000),
        ("kraken", "BTC-USD", 100_010),
        ("coinbase", "DOGE-USD", 0.15),
        ("kraken", "DOGE-USD", 0.16),
    )
    assert not desk.matches(_opp(symbol="BTC-USD"), book)
    assert desk.matches(_opp(symbol="DOGE-USD"), book)
    assert desk.quote_ok(_quote("coinbase", "DOGE-USD", 0.15), book)
    assert not desk.quote_ok(_quote("coinbase", "BTC-USD", 100_000), book)


def test_over_filter_hides_cheap_pairs() -> None:
    desk = TradeDesk(assets=["BTC", "DOGE"])
    desk.apply({"price_mode": "over", "price_limit": 5})
    book = _book(
        ("coinbase", "BTC-USD", 100_000),
        ("kraken", "BTC-USD", 100_010),
        ("coinbase", "DOGE-USD", 0.15),
        ("kraken", "DOGE-USD", 0.16),
    )
    assert desk.matches(_opp(symbol="BTC-USD"), book)
    assert not desk.matches(_opp(symbol="DOGE-USD"), book)


def test_ratio_pairs_use_coin_usd_price_not_the_ratio() -> None:
    desk = TradeDesk(all_assets=True)
    desk.apply({"price_mode": "under", "price_limit": 5})
    book = _book(
        ("coinbase", "ETH-BTC", 0.03),
        ("coinbase", "ETH-USD", 3_000),
        ("coinbase", "BTC-USD", 100_000),
    )
    triangle = _opp(kind=OpportunityKind.TRIANGULAR, venues=("coinbase", "coinbase"), symbol="ETH-BTC")
    assert not desk.matches(triangle, book)
    assert not desk.quote_ok(_quote("coinbase", "ETH-BTC", 0.03), book)


def test_price_filter_hides_unknown_usd_price() -> None:
    desk = TradeDesk(all_assets=True)
    desk.apply({"price_mode": "under", "price_limit": 5})
    book = _book(("coinbase", "BTC-USD", 100_000))
    assert not desk.matches(_opp(symbol="DOGE-USD"), book)


def test_any_price_keeps_expensive_pairs() -> None:
    desk = TradeDesk()
    book = _book(("coinbase", "BTC-USD", 100_000), ("kraken", "BTC-USD", 100_010))
    assert desk.matches(_opp(), book)


def test_price_mode_and_limit_clamp() -> None:
    desk = TradeDesk()
    desk.apply({"price_mode": "nope", "price_limit": 0})
    assert desk.price_mode == "any"
    assert desk.price_limit == 0.01
    desk.apply({"price_mode": "UNDER", "price_limit": 5})
    assert desk.price_mode == "under"
    assert desk.price_limit == 5
    assert 5 in desk.to_dict()["price_presets"]


def test_snapshot_quotes_respect_price_filter() -> None:
    engine = Engine(AppConfig())
    engine.desk.apply({"price_mode": "under", "price_limit": 5})
    engine.book.update(_quote("coinbase", "BTC-USD", 100_000))
    engine.book.update(_quote("coinbase", "DOGE-USD", 0.12))
    symbols = {row["canonical"] for row in engine.snapshot()["quotes"]}
    assert "DOGE-USD" in symbols
    assert "BTC-USD" not in symbols


@pytest.mark.asyncio
async def test_invest_blocked_by_price_filter() -> None:
    engine = Engine(AppConfig())
    engine.desk.apply({"price_mode": "under", "price_limit": 5, "all_assets": True})
    engine.book.update(_quote("coinbase", "BTC-USD", 100_000))
    engine.book.update(_quote("kraken", "BTC-USD", 100_010))
    opp = _opp()
    engine.by_id[opp.id] = opp
    result = await engine.invest(opp.id)
    assert result["ok"] is False
    assert "price filter" in result["error"].lower()
