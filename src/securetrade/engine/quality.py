from __future__ import annotations

from securetrade.models import Opportunity, TrustBreakdown


def quality_score(opportunity: Opportunity, trust: TrustBreakdown, execution_probability: float) -> float:
    """Expected Net Edge × P(success) × Liquidity × Security Confidence.

    A 0.30% high-quality opportunity can outrank a suspicious 15% discrepancy.
    """
    edge = max(0.0, (opportunity.expected_net_edge_bps or opportunity.net_edge_bps) / 10_000)
    liquidity = min(1.0, max(0.05, (opportunity.liquidity_usd or opportunity.notional) / 10_000))
    security = max(0.0, trust.score / 100)
    probability = max(0.0, min(1.0, execution_probability))
    return edge * probability * liquidity * security


def rank_opportunities(items: list[tuple[Opportunity, TrustBreakdown, float]]) -> list[Opportunity]:
    scored: list[tuple[float, Opportunity]] = []
    for opportunity, trust, probability in items:
        score = quality_score(opportunity, trust, probability)
        scored.append((score, opportunity.with_updates(quality_score=score)))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored]
