from __future__ import annotations

from securetrade.engine.consensus import ConsensusResult
from securetrade.engine.simulate import SimulationResult
from securetrade.models import Opportunity, TrustBreakdown


def explain_trade(
    opportunity: Opportunity,
    trust: TrustBreakdown,
    consensus: ConsensusResult,
    simulation: SimulationResult,
    within_limits: bool,
) -> list[str]:
    lines: list[str] = []
    if opportunity.confluence:
        aligned = ", ".join(opportunity.timeframes_aligned) or opportunity.timeframe
        lines.append(f"{opportunity.confluence} timeframes aligned {opportunity.side.upper() or 'IN'} ({aligned})")
    if opportunity.pattern:
        lines.append(f"Pattern: {opportunity.pattern}")
    if opportunity.side and opportunity.entry_price:
        lines.append(
            f"{opportunity.side.upper()} entry {opportunity.entry_price:.6g} · stop {opportunity.stop_price:.6g} · target {opportunity.target_price:.6g}"
        )
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
    if trust.label:
        lines.append(f"Trust {trust.score}/100 — {trust.label}")
    for note in consensus.notes:
        if note not in lines:
            lines.append(note)
    return lines


def why_blocked(guardian_reasons: list[str]) -> list[str]:
    return list(guardian_reasons)
