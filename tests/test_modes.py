import pytest

from securetrade.config import AppConfig
from securetrade.engine.forced import make_forced_opportunity
from securetrade.engine.runner import Engine
from securetrade.models import OperatingMode


@pytest.mark.asyncio
async def test_assist_mode_queues_for_approval() -> None:
    engine = Engine(AppConfig())
    engine.set_mode(OperatingMode.ASSIST)
    opp = make_forced_opportunity(engine.book, "captured")
    wrapped = await engine.ingest(opp)
    assert wrapped.result.pending_approval is True
    assert opp.id in engine.pending
    approved = await engine.approve(opp.id)
    assert approved["ok"] is True
