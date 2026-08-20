import pytest

from pulsearb.config import AppConfig
from pulsearb.engine.desk import TradeDesk, opportunity_assets
from pulsearb.engine.runner import Engine
from pulsearb.models import Leg, Opportunity, OpportunityKind


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
    assert engine.paper.pnl > 0
    assert list(engine.fills)[0].notional == 15
