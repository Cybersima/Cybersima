from __future__ import annotations

import time
from dataclasses import dataclass

from securetrade.engine.book import MarketBook
from securetrade.engine.capital import CapitalProtection
from securetrade.engine.consensus import PriceConsensus
from securetrade.engine.forex import is_forex_kind
from securetrade.engine.guardian import Guardian
from securetrade.engine.paper_lab import PaperLab
from securetrade.engine.quality import quality_score
from securetrade.engine.recovery_commit import RecoveryCommit, handoff_state
from securetrade.engine.regime import RegimeDetector
from securetrade.engine.scam import ScamDefense
from securetrade.engine.simulate import simulate_fill
from securetrade.engine.trust import TrustEngine
from securetrade.engine.why import explain_trade
from securetrade.journal import DecisionJournal
from securetrade.models import (
    CommitDecision,
    HandoffState,
    OperatingMode,
    Opportunity,
    PaperOutcome,
    PaperPosition,
    RecoveryCommitRecord,
)


@dataclass
class PipelineResult:
    opportunity: Opportunity
    handoff: str
    commit: RecoveryCommitRecord | None
    position: PaperPosition | None
    blocked: bool
    pending_approval: bool


class TradingPipeline:
    """SCAN → DETECT → VERIFY → SECURITY SCREEN → RISK SCORE → SIMULATE → HANDOFF → COMMIT → PAPER LAB."""

    def __init__(
        self,
        guardian: Guardian,
        capital: CapitalProtection,
        journal: DecisionJournal,
        paper_lab: PaperLab,
        mode: OperatingMode = OperatingMode.LEARN,
    ) -> None:
        self.guardian = guardian
        self.capital = capital
        self.journal = journal
        self.paper_lab = paper_lab
        self.consensus = PriceConsensus()
        self.trust = TrustEngine()
        self.scam = ScamDefense()
        self.commit_gate = RecoveryCommit()
        self.regime = RegimeDetector()
        self.mode = mode
        self.approvals: set[str] = set()
        self.commits: list[RecoveryCommitRecord] = []

    def evaluate(self, opportunity: Opportunity, book: MarketBook, now: float | None = None) -> PipelineResult:
        now = now or time.time()
        consensus = self.consensus.evaluate(opportunity, book, now=now)
        scam = self.scam.inspect(opportunity)
        simulation = simulate_fill(opportunity, book)
        regime = self.regime.classify(opportunity, book)
        opportunity = opportunity.with_updates(
            estimated_slippage_bps=simulation.expected_slippage_bps,
            expected_net_edge_bps=simulation.expected_net_edge_bps or opportunity.net_edge_bps,
            expected_gross_spread_bps=opportunity.edge_bps,
            estimated_fees_bps=opportunity.edge_bps - opportunity.net_edge_bps,
            liquidity_usd=max(opportunity.liquidity_usd, opportunity.notional * 8),
            max_anticipated_loss=opportunity.notional * 0.01,
            regime=regime.value,
        )
        trust = self.trust.score(opportunity, consensus, scam)
        base_probability = 0.9 if simulation.viable and opportunity.executable else 0.45
        probability = (
            opportunity.execution_confidence
            if 0 < opportunity.execution_confidence < base_probability
            else base_probability
        )
        qscore = quality_score(opportunity, trust, probability)
        opportunity = opportunity.with_updates(
            trust_score=trust.score,
            security_score=int(round(trust.security_indicators * 100)),
            execution_confidence=probability,
            quality_score=qscore,
        )
        verdict = self.guardian.decide(opportunity, trust, consensus, scam, simulation, regime.value)
        capital = self.capital.allow(opportunity, confidence=probability)
        within_limits = capital.allowed
        why = explain_trade(opportunity, trust, consensus, simulation, within_limits)
        opportunity = opportunity.with_updates(
            why=why,
            why_blocked=list(verdict.reasons) + ([] if within_limits else [capital.reason]),
            guardian_allowed=verdict.allowed and within_limits,
        )
        pending = self.mode is OperatingMode.ASSIST and opportunity.id not in self.approvals
        state = handoff_state(self.mode, opportunity.guardian_allowed, pending)
        self.journal.record(
            action="evaluate",
            opportunity_id=opportunity.id,
            decision=state.value,
            sources=[leg.venue for leg in opportunity.legs],
            expected_profit=opportunity.notional * (opportunity.expected_net_edge_bps / 10_000),
            actual_result=None,
            risk_score=trust.score,
            security_decision="ALLOW" if verdict.allowed else "BLOCK",
            details={
                "guardian": verdict.to_dict(),
                "consensus": consensus.to_dict(),
                "simulation": simulation.to_dict(),
                "trust": trust.to_dict(),
            },
            ts=now,
        )
        if state is HandoffState.BLOCKED:
            return PipelineResult(opportunity, state.value, None, None, True, False)
        if state is HandoffState.PENDING_APPROVAL:
            return PipelineResult(opportunity, state.value, None, None, False, True)

        ages = _ages(opportunity, book, now)
        record = self.commit_gate.evaluate(
            opportunity,
            simulation,
            confirmation_age_ms=ages["confirmation_age_ms"],
            book_age_ms=ages["book_age_ms"],
            latency_skew_ms=ages["latency_skew_ms"],
            detected_edge_bps=opportunity.net_edge_bps,
            now=now,
        )
        self.commits.append(record)
        self.journal.record(
            action="recovery_commit",
            opportunity_id=opportunity.id,
            decision=record.decision,
            sources=[leg.venue for leg in opportunity.legs],
            expected_profit=opportunity.notional * (record.commit_edge_bps / 10_000),
            actual_result=None,
            risk_score=trust.score,
            security_decision=record.decision,
            details=record.to_dict(),
            ts=now,
        )
        if record.decision == CommitDecision.CANCEL.value:
            return PipelineResult(opportunity, state.value, record, None, False, False)

        expected_pnl = opportunity.notional * (record.commit_edge_bps / 10_000)
        position = self.paper_lab.open_from_opportunity(
            opportunity_id=opportunity.id,
            pair=opportunity.pair or (opportunity.legs[0].symbol if opportunity.legs else ""),
            notional=opportunity.notional,
            expected_pnl=expected_pnl,
            commit_kind=record.decision,
            expected_net_edge_bps=record.commit_edge_bps,
            trust_score=trust.score,
            now=now,
            timeout_seconds=0.0 if is_forex_kind(opportunity.kind) else None,
            side=opportunity.side,
            entry_price=opportunity.entry_price,
            stop_price=opportunity.stop_price,
            target_price=opportunity.target_price,
            timeframe=opportunity.timeframe,
            asset_class="fx" if is_forex_kind(opportunity.kind) else "",
        )
        return PipelineResult(opportunity, state.value, record, position, False, False)

    def approve(self, opportunity_id: str) -> None:
        self.approvals.add(opportunity_id)

    def close_forced(self, opportunity_id: str, outcome: PaperOutcome, pnl: float, note: str = "") -> PaperPosition:
        position = self.paper_lab.force(opportunity_id, outcome, pnl, note)
        self.journal.record(
            action="paper_lab_close",
            opportunity_id=opportunity_id,
            decision=outcome.value,
            sources=[],
            expected_profit=position.expected_pnl,
            actual_result=pnl,
            risk_score=position.trust_score,
            security_decision=outcome.value,
            details=position.to_dict(),
        )
        return position


def _ages(opportunity: Opportunity, book: MarketBook, now: float) -> dict[str, float]:
    quotes = [book.get(leg.venue, leg.symbol) for leg in opportunity.legs]
    quotes = [q for q in quotes if q is not None]
    if not quotes:
        return {"confirmation_age_ms": 0.0, "book_age_ms": 0.0, "latency_skew_ms": 0.0}
    ages = [(now - q.ts) * 1000 for q in quotes]
    latencies = [q.latency_ms for q in quotes]
    skew = (max(latencies) - min(latencies)) if latencies else 0.0
    if not skew:
        skew = max(ages) - min(ages)
    return {
        "confirmation_age_ms": max(ages),
        "book_age_ms": max(ages),
        "latency_skew_ms": skew,
    }
