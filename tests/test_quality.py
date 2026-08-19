from securetrade.engine.quality import quality_score, rank_opportunities
from securetrade.models import Leg, Opportunity, OpportunityKind, TrustBreakdown


def _opp(edge: float, liq: float, oid: str) -> Opportunity:
    return Opportunity(
        kind=OpportunityKind.CROSS_VENUE,
        edge_bps=edge,
        net_edge_bps=edge,
        expected_net_edge_bps=edge,
        notional=250,
        legs=[Leg("buy", "coinbase", "BTC-USD", 1, True)],
        summary=oid,
        executable=True,
        ts=0,
        id=oid,
        pair="BTC/USDC",
        liquidity_usd=liq,
    )


def _trust(score: int) -> TrustBreakdown:
    return TrustBreakdown(score, "x", 1, 1, 1, 1, 1, 1, 1, 1, 1)


def test_quality_prefers_small_clean_edge_over_suspicious_spike() -> None:
    clean = _opp(30, 50_000, "clean")  # 0.30%
    spike = _opp(1500, 200, "spike")  # 15%
    clean_trust = _trust(96)
    spike_trust = _trust(22)
    ranked = rank_opportunities(
        [
            (spike, spike_trust, 0.2),
            (clean, clean_trust, 0.91),
        ]
    )
    assert ranked[0].id == "clean"
    assert quality_score(clean, clean_trust, 0.91) > quality_score(spike, spike_trust, 0.2)
