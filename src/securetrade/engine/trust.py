from __future__ import annotations

from securetrade.engine.consensus import VENUE_RELIABILITY, ConsensusResult
from securetrade.engine.scam import ScamReport
from securetrade.models import Opportunity, TrustBreakdown


KNOWN_ASSETS = {
    "BTC": 1.0,
    "ETH": 0.98,
    "SOL": 0.9,
    "XRP": 0.86,
    "ADA": 0.84,
    "LTC": 0.88,
    "LINK": 0.9,
    "USD": 1.0,
    "USDT": 0.92,
    "USDC": 0.96,
    "EUR": 1.0,
}


def _label(score: int) -> str:
    if score >= 85:
        return "Low Risk"
    if score >= 70:
        return "Moderate Risk"
    if score >= 55:
        return "Elevated Risk"
    return "High Risk"


class TrustEngine:
    """CyberSym Trust Score: 0–100 combining venue, asset, liquidity, and security."""

    def score(
        self,
        opportunity: Opportunity,
        consensus: ConsensusResult,
        scam: ScamReport | None = None,
        volatility_bps: float = 12.0,
    ) -> TrustBreakdown:
        venues = [leg.venue for leg in opportunity.legs] or ["simulator"]
        venue_rel = sum(VENUE_RELIABILITY.get(v, 0.6) for v in venues) / len(venues)
        pair = (opportunity.pair or "").replace("/", "-").upper()
        assets = pair.split("-") if pair else []
        asset_rep = 0.7
        if assets:
            asset_rep = sum(KNOWN_ASSETS.get(a, 0.45) for a in assets) / len(assets)
        liquidity = min(1.0, (opportunity.liquidity_usd or opportunity.notional * 20) / 20_000)
        book_quality = 1.0
        if opportunity.estimated_slippage_bps > 8:
            book_quality = 0.55
        elif opportunity.estimated_slippage_bps > 3:
            book_quality = 0.78
        vol = max(0.2, 1.0 - min(volatility_bps, 80) / 100)
        consistency = min(1.0, 0.4 + 0.2 * consensus.sources)
        if consensus.outlier_venues:
            consistency *= 0.6
        if consensus.stale_venues:
            consistency *= 0.75
        abnormal = 0.35 if consensus.outlier_venues else 1.0
        security = 1.0
        if scam and not scam.clean:
            security = 0.15 if scam.critical else 0.45
        exec_risk = min(1.0, opportunity.execution_confidence or (0.55 if opportunity.executable else 0.3))
        weighted = (
            venue_rel * 0.14
            + asset_rep * 0.12
            + liquidity * 0.12
            + book_quality * 0.10
            + vol * 0.10
            + consistency * 0.12
            + abnormal * 0.10
            + security * 0.12
            + exec_risk * 0.08
        )
        score = int(round(max(0.0, min(1.0, weighted)) * 100))
        return TrustBreakdown(
            score=score,
            label=_label(score),
            venue_reliability=round(venue_rel, 3),
            asset_reputation=round(asset_rep, 3),
            liquidity=round(liquidity, 3),
            book_quality=round(book_quality, 3),
            volatility=round(vol, 3),
            data_consistency=round(consistency, 3),
            abnormal_behavior=round(abnormal, 3),
            security_indicators=round(security, 3),
            execution_risk=round(exec_risk, 3),
        )
