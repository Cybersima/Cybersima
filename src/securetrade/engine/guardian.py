from __future__ import annotations

from securetrade.engine.consensus import ConsensusResult
from securetrade.engine.scam import ScamReport
from securetrade.engine.simulate import SimulationResult
from securetrade.models import GuardianVerdict, MarketRegime, Opportunity, TrustBreakdown


class Guardian:
    """CyberSym Guardian™ sits above the trading engine.

    The profit engine asks: "Can I make this trade?"
    Guardian asks: "Should I allow this trade?"
    """

    def __init__(self, settings: dict | None = None) -> None:
        settings = settings or {}
        self.min_trust_score = int(settings.get("min_trust_score", 55))
        self.block_below_trust = int(settings.get("block_below_trust", 40))
        self.require_consensus = bool(settings.get("require_consensus", True))
        self.block_abnormal_regime = bool(settings.get("block_abnormal_regime", True))

    def decide(
        self,
        opportunity: Opportunity,
        trust: TrustBreakdown,
        consensus: ConsensusResult,
        scam: ScamReport,
        simulation: SimulationResult | None = None,
        regime: str = MarketRegime.NORMAL.value,
    ) -> GuardianVerdict:
        reasons: list[str] = []
        severity = "info"
        if scam.critical:
            reasons.extend(scam.findings or ["Asset failed trust requirements"])
            severity = "CRITICAL"
        elif not scam.clean:
            reasons.extend(scam.findings)
            severity = "HIGH"
        if trust.score < self.block_below_trust:
            reasons.append("Asset failed trust requirements")
            severity = "CRITICAL"
        elif trust.score < self.min_trust_score:
            reasons.append(f"Trust score {trust.score}/100 below policy")
            severity = "HIGH" if severity == "info" else severity
        if self.require_consensus and not consensus.ok:
            reasons.append("Price consensus failed — unreliable sources")
            severity = "HIGH" if severity == "info" else severity
        if consensus.outlier_venues:
            reasons.append("Abnormal price divergence")
            if severity == "info":
                severity = "HIGH"
        if trust.abnormal_behavior < 0.5:
            reasons.append("Unusual liquidity behavior")
            if severity == "info":
                severity = "HIGH"
        if trust.security_indicators < 0.4:
            reasons.append("Counterparty risk elevated")
            severity = "CRITICAL"
        if simulation and not simulation.viable:
            # Simulation remains an advisory input; Final Commit decides CANCEL vs Paper Lab.
            reasons.append("Pre-trade simulation flagged thin liquidity")
        if self.block_abnormal_regime and regime == MarketRegime.ABNORMAL.value:
            reasons.append("Potential manipulation detected")
            severity = "CRITICAL"
        if opportunity.net_edge_bps > 500 and trust.score < 80:
            reasons.append("Spectacular discrepancy failed security validation")
            severity = "CRITICAL"
        allowed = not reasons or severity == "info"
        if reasons and severity in {"HIGH", "CRITICAL"}:
            allowed = False
        if not allowed and severity == "CRITICAL" and not reasons:
            reasons = ["Security policy rejected this opportunity"]
        return GuardianVerdict(allowed=allowed, severity=severity if not allowed else "info", reasons=reasons)
