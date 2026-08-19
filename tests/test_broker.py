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
