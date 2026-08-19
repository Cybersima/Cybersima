from securetrade.engine.book import MarketBook
from securetrade.engine.consensus import ConsensusResult
from securetrade.engine.forced import make_quote
from securetrade.engine.health import HealthMonitor
from securetrade.engine.regime import RegimeDetector
from securetrade.engine.simulate import SimulationResult
from securetrade.engine.why import explain_trade
from securetrade.models import KillSource, Leg, Opportunity, OpportunityKind, TrustBreakdown


def test_why_this_trade_lists_controls() -> None:
    opp = Opportunity(
        kind=OpportunityKind.CROSS_VENUE,
        edge_bps=40,
        net_edge_bps=31,
        notional=250,
        legs=[Leg("buy", "coinbase", "BTC-USD", 1, True)],
        summary="btc",
        executable=True,
        ts=0,
        id="w",
        pair="BTC/USDC",
        liquidity_usd=40000,
    )
    trust = TrustBreakdown(92, "Low Risk", 1, 1, 1, 1, 1, 1, 1, 1, 1)
    consensus = ConsensusResult(True, 3, 97000, [], [], [], 12, {}, ["Multiple markets confirmed price"])
    sim = SimulationResult(True, 250, 1.2, 28, ["Strong liquidity"])
    lines = explain_trade(opp, trust, consensus, sim, True)
    joined = " ".join(lines).lower()
    assert "fees calculated" in joined
    assert "within your risk limits" in joined
    assert "92/100" in joined
    assert "expected about $" in joined


def test_abnormal_regime_on_spectacular_edge() -> None:
    book = MarketBook()
    book.update(make_quote("coinbase", "BTC-USD", 97000, 97010))
    opp = Opportunity(
        kind=OpportunityKind.CROSS_VENUE,
        edge_bps=900,
        net_edge_bps=874,
        notional=250,
        legs=[Leg("buy", "coinbase", "BTC-USD", 97010, True)],
        summary="x",
        executable=True,
        ts=0,
        id="abn",
        pair="BTC-USD",
    )
    assert RegimeDetector().classify(opp, book).value == "abnormal"


def test_health_flags_stale_and_disconnect() -> None:
    report = HealthMonitor().report({"coinbase": "error: timeout"}, stale_feeds=["kraken"])
    assert report.ok is False
    assert "stale price feed" in report.issues
    assert report.api_connectivity == "degraded"


def test_admin_lock_cannot_be_customer_resumed() -> None:
    from securetrade.engine.risk import RiskManager

    risk = RiskManager()
    risk.admin_lock()
    assert risk.killed
    assert risk.resume(KillSource.CUSTOMER) is False
    assert risk.resume(KillSource.ADMIN) is True
