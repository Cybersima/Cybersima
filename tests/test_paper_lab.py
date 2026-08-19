import time

from securetrade.engine.paper_lab import PaperLab
from securetrade.engine.recovery_commit import RecoveryCommit
from securetrade.engine.simulate import SimulationResult
from securetrade.models import CommitDecision, Leg, Opportunity, OpportunityKind, PaperOutcome


def test_paper_lab_expire_and_miss() -> None:
    lab = PaperLab(timeout_seconds=0.01)
    pos = lab.open_from_opportunity("oid", "BTC/USDC", 250, 1.0, "COMMIT", 20, 90, now=time.time() - 1)
    assert pos is not None
    expired = lab.expire_open()
    assert expired[0].outcome == PaperOutcome.EXPIRED.value
    lab.open_from_opportunity("oid2", "BTC/USDC", 250, 1.0, "COMMIT", 20, 90)
    missed = lab.resolve_against_edge("oid2", live_edge_bps=0)
    assert missed and missed.outcome == PaperOutcome.MISSED.value
    cancelled = lab.open_from_opportunity("oid3", "BTC/USDC", 250, 1.0, "CANCEL", 20, 90)
    assert cancelled is None


def test_recovery_commit_decisions() -> None:
    gate = RecoveryCommit()
    opp = Opportunity(
        kind=OpportunityKind.CROSS_VENUE,
        edge_bps=40,
        net_edge_bps=30,
        notional=250,
        legs=[Leg("buy", "coinbase", "BTC-USD", 1, True), Leg("sell", "kraken", "XBTUSD", 1, True)],
        summary="x",
        executable=True,
        ts=0,
        id="r",
        pair="BTC/USDC",
        execution_confidence=0.9,
    )
    good = SimulationResult(True, 250, 1.0, 28.0, [])
    rec = gate.evaluate(opp, good, 100, 100, 10, 30)
    assert rec.decision == CommitDecision.COMMIT.value
    dead = SimulationResult(False, 0, 20, -1.0, [])
    rec2 = gate.evaluate(opp, dead, 100, 100, 10, 30)
    assert rec2.decision == CommitDecision.CANCEL.value
    rec3 = gate.evaluate(opp, good, 4000, 100, 10, 30)
    assert rec3.decision == CommitDecision.CANCEL.value
    low = opp.with_updates(execution_confidence=0.4)
    rec4 = gate.evaluate(low, good, 100, 100, 10, 30)
    assert rec4.decision == CommitDecision.RESEARCH_COMMIT.value
