from __future__ import annotations

import time

from securetrade.engine.simulate import SimulationResult
from securetrade.engine.forex import is_forex_kind
from securetrade.models import CommitDecision, HandoffState, OperatingMode, Opportunity, RecoveryCommitRecord


class RecoveryCommit:
    """v0.3.8b Final Commit — measurement and advisory gate, not a replacement for Paper Lab.

    ATOMIC_READY → COMMIT / RESEARCH_COMMIT / CANCEL
    CANCEL does not enter Paper Lab.
    """

    def evaluate(
        self,
        opportunity: Opportunity,
        simulation: SimulationResult,
        confirmation_age_ms: float,
        book_age_ms: float,
        latency_skew_ms: float,
        detected_edge_bps: float,
        now: float | None = None,
    ) -> RecoveryCommitRecord:
        now = now or time.time()
        commit_edge = simulation.expected_net_edge_bps
        retention = 0.0 if detected_edge_bps == 0 else max(0.0, commit_edge / detected_edge_bps)
        atomic = opportunity.executable and simulation.viable and len(opportunity.legs) >= 2
        forex = is_forex_kind(opportunity.kind)
        age_limit = 12_000 if forex else 2500
        book_limit = 15_000 if forex else 4000
        skew_limit = 6_000 if forex else 800
        decision = CommitDecision.COMMIT
        note = "Eligible for original Paper Lab path"
        if not simulation.viable or commit_edge <= 0:
            decision = CommitDecision.CANCEL
            note = "Edge collapsed or book not fillable — never enters Paper Lab"
        elif confirmation_age_ms > age_limit or book_age_ms > book_limit or latency_skew_ms > skew_limit:
            decision = CommitDecision.CANCEL
            note = "Freshness/latency failed Final Commit"
        elif retention < 0.55 or opportunity.execution_confidence < 0.55:
            decision = CommitDecision.RESEARCH_COMMIT
            note = "Advisory research commit — still eligible for Paper Lab"
        elif not atomic:
            decision = CommitDecision.RESEARCH_COMMIT
            note = "Non-atomic legs — research commit"
        return RecoveryCommitRecord(
            opportunity_id=opportunity.id,
            decision=decision.value,
            commit_edge_bps=round(commit_edge, 4),
            edge_retention=round(retention, 4),
            confirmation_age_ms=round(confirmation_age_ms, 2),
            book_age_ms=round(book_age_ms, 2),
            latency_skew_ms=round(latency_skew_ms, 2),
            atomic_fill=atomic,
            ts=now,
            note=note,
        )


def handoff_state(mode: OperatingMode, guardian_allowed: bool, pending_approval: bool) -> HandoffState:
    if not guardian_allowed:
        return HandoffState.BLOCKED
    if mode is OperatingMode.ASSIST and pending_approval:
        return HandoffState.PENDING_APPROVAL
    return HandoffState.ATOMIC_READY
