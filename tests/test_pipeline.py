import pytest

from securetrade.config import AppConfig
from securetrade.engine.runner import Engine
from securetrade.models import CommitDecision, OperatingMode, PaperOutcome


@pytest.fixture
def engine() -> Engine:
    config = AppConfig()
    config.env.demo_only = True
    config._apply_env_overrides()
    eng = Engine(config)
    eng.set_mode(OperatingMode.LEARN)
    return eng


@pytest.mark.asyncio
async def test_forced_profitable_capture(engine: Engine) -> None:
    closed = await engine.force_outcome("captured")
    assert closed.outcome == PaperOutcome.CAPTURED.value
    assert closed.actual_pnl > 0
    assert closed.commit_kind in {CommitDecision.COMMIT.value, CommitDecision.RESEARCH_COMMIT.value}
    assert engine.stats.captured >= 1
    assert engine.stats.paper_opened >= 1
    assert engine.stats.handoff_atomic_ready >= 1
    assert engine.paper.pnl > 0
    tones = {q["canonical"]: q.get("tone") for q in engine.snapshot()["quotes"]}
    assert tones.get("BTC-USD") == "profit"


@pytest.mark.asyncio
async def test_forced_reversal_closes_negative(engine: Engine) -> None:
    closed = await engine.force_outcome("reversed")
    assert closed.outcome == PaperOutcome.REVERSED.value
    assert closed.actual_pnl < 0
    assert engine.stats.reversed >= 1
    tones = {q["canonical"]: q.get("tone") for q in engine.snapshot()["quotes"]}
    assert tones.get("BTC-USD") == "reversal"


@pytest.mark.asyncio
async def test_research_commit_still_enters_paper_lab(engine: Engine) -> None:
    closed = await engine.force_outcome("research")
    assert closed.commit_kind == CommitDecision.RESEARCH_COMMIT.value
    assert closed.outcome == PaperOutcome.CAPTURED.value
    assert engine.stats.recovery_research_pass >= 1
    assert engine.stats.paper_opened >= 1


@pytest.mark.asyncio
async def test_cancelled_trade_never_enters_paper_lab(engine: Engine) -> None:
    closed = await engine.force_outcome("cancel")
    assert closed.outcome == PaperOutcome.CANCELLED.value
    assert closed.commit_kind == CommitDecision.CANCEL.value
    assert engine.stats.recovery_cancel >= 1
    assert all(item.opportunity_id != closed.opportunity_id for item in engine.paper_lab.closed)
    assert closed.opportunity_id not in engine.paper_lab.open
