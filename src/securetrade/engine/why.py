from __future__ import annotations

from securetrade.engine.consensus import ConsensusResult
from securetrade.engine.simulate import SimulationResult
from securetrade.engine.starter import expected_dollars
from securetrade.models import Opportunity, TrustBreakdown


def explain_trade(
    opportunity: Opportunity,
    trust: TrustBreakdown,
    consensus: ConsensusResult,
    simulation: SimulationResult,
    within_limits: bool,
) -> list[str]:
    lines: list[str] = []
    if consensus.sources >= 2:
        lines.append("Multiple markets confirmed price")
    if simulation.viable and opportunity.liquidity_usd >= opportunity.notional:
        lines.append("Strong liquidity")
    lines.append("Fees calculated")
    if simulation.expected_slippage_bps < 8:
        lines.append("Slippage acceptable")
    if trust.security_indicators >= 0.8 and not opportunity.why_blocked:
        lines.append("No security anomalies")
    if within_limits:
        lines.append("Within your risk limits")
    profit = expected_dollars(opportunity.notional, opportunity.expected_net_edge_bps or opportunity.net_edge_bps)
    lines.append(f"Expected about ${profit:.2f} on this ${opportunity.notional:.0f} ticket")
    if trust.label:
        lines.append(f"Trust {trust.score}/100 — {trust.label}")
    for note in consensus.notes:
        if note not in lines:
            lines.append(note)
    return lines


def why_blocked(guardian_reasons: list[str]) -> list[str]:
    return list(guardian_reasons)


def customer_details(opportunity: Opportunity) -> dict:
    """Plain-language 'Why this trade?' card. Never a raw dump of internals."""
    edge = opportunity.expected_net_edge_bps or opportunity.net_edge_bps
    profit = expected_dollars(opportunity.notional, edge)
    legs = [f"{leg.action.title()} {leg.symbol} on {leg.venue} @ {leg.price:g}" for leg in opportunity.legs]
    return {
        "title": opportunity.pair or "Opportunity",
        "headline": "Why this trade?",
        "summary": opportunity.summary,
        "ticket_usd": round(opportunity.notional, 2),
        "expected_net_edge_pct": round(edge / 100, 4),
        "expected_profit_usd": profit,
        "max_anticipated_loss_usd": round(opportunity.max_anticipated_loss or opportunity.notional * 0.01, 4),
        "fees_pct": round(opportunity.estimated_fees_bps / 100, 4),
        "slippage_pct": round(opportunity.estimated_slippage_bps / 100, 4),
        "trust_score": opportunity.trust_score,
        "security_score": opportunity.security_score or opportunity.trust_score,
        "execution_confidence_pct": round(opportunity.execution_confidence * 100, 1),
        "guardian": "Allowed" if opportunity.guardian_allowed else "Blocked",
        "legs": legs,
        "why": list(opportunity.why),
        "why_blocked": list(opportunity.why_blocked),
        "honest_note": (
            f"If this ${opportunity.notional:.0f} ticket captures a {edge / 100:.2f}% net edge, "
            f"expected profit is about ${profit:.2f}. That is not a guarantee. "
            "Fees, slippage, or a missed leg can turn it into a loss. Guardian can still walk away."
        ),
    }
