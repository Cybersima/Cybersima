import pytest

from pulsearb.engine.broker import PaperBroker
from pulsearb.engine.risk import RiskManager
from pulsearb.models import Leg, Opportunity, OpportunityKind


def _opp(executable: bool = True, notional: float = 50) -> Opportunity:
    return Opportunity(
        kind=OpportunityKind.TRIANGULAR,
        edge_bps=40,
        net_edge_bps=28,
        notional=notional,
        legs=[
            Leg("buy", "binance", "ETHBTC", 0.0191, True),
            Leg("sell", "binance", "ETHUSDT", 2000, True),
        ],
        summary="test",
        executable=executable,
        ts=0,
        id="abc",
    )


@pytest.mark.asyncio
async def test_paper_fill_increases_pnl() -> None:
    risk = RiskManager(max_notional_usdt=250, cooldown_seconds=0)
    broker = PaperBroker(risk)
    fills = await broker.execute(_opp())
    assert fills[0].status == "filled"
    assert broker.pnl > 0


@pytest.mark.asyncio
async def test_kill_switch_blocks() -> None:
    risk = RiskManager(cooldown_seconds=0)
    risk.kill()
    broker = PaperBroker(risk)
    fills = await broker.execute(_opp())
    assert fills[0].status == "blocked"


@pytest.mark.asyncio
async def test_alert_not_traded() -> None:
    broker = PaperBroker(RiskManager(cooldown_seconds=0))
    fills = await broker.execute(_opp(executable=False))
    assert fills[0].status == "alert_only"


def test_notional_cap() -> None:
    risk = RiskManager(max_notional_usdt=10, cooldown_seconds=0)
    decision = risk.allow(50)
    assert not decision.allowed


def test_cooldown_block_helper_ignores_fills() -> None:
    from pulsearb.engine.runner import _cooldown_block
    from pulsearb.models import Fill

    blocked = [
        Fill(
            venue="paper",
            symbol="-",
            side="blocked",
            qty=0,
            price=0,
            notional=0,
            ts=0,
            paper=True,
            opportunity_id="x",
            status="blocked",
            note="cooldown",
        )
    ]
    filled = [
        Fill(
            venue="coinbase",
            symbol="BTC-USD",
            side="buy",
            qty=0.001,
            price=100000,
            notional=100,
            ts=0,
            paper=True,
            opportunity_id="x",
            status="filled",
            note="paper fill",
        )
    ]
    assert _cooldown_block(blocked) is True
    assert _cooldown_block(filled) is False
    assert _cooldown_block([]) is False


@pytest.mark.asyncio
async def test_paper_usd_triangle_chains_cash_pnl() -> None:
    from pulsearb.engine.money import cash_pnl

    risk = RiskManager(max_notional_usdt=250, cooldown_seconds=0)
    broker = PaperBroker(risk)
    opp = Opportunity(
        kind=OpportunityKind.TRIANGULAR,
        edge_bps=250,
        net_edge_bps=98,
        notional=1,
        legs=[
            Leg("buy", "coinbase", "BTC-USD", 100010, True),
            Leg("buy", "coinbase", "ETH-BTC", 0.01951, True),
            Leg("sell", "coinbase", "ETH-USD", 2000, True),
        ],
        summary="USD → BTC → ETH → USD",
        executable=True,
        ts=0,
        id="usd-tri",
    )
    fills = await broker.execute(opp)
    assert all(item.status == "filled" for item in fills)
    realized = cash_pnl(fills)
    assert abs(realized) < 0.5
    assert realized == pytest.approx(broker.pnl, abs=1e-9)


def test_live_budget_splits_across_taps() -> None:
    risk = RiskManager(max_notional_usdt=25, live_budget_usdt=25, cooldown_seconds=0, min_notional_usdt=1)
    assert risk.allow(1).allowed
    assert risk.allow(5).allowed
    risk.reserve_live(5)
    assert risk.remaining_budget() == 20
    assert risk.taps_left(5) == 4
    risk.reserve_live(20)
    blocked = risk.allow(5)
    assert blocked.allowed is False
    assert "budget" in blocked.reason
