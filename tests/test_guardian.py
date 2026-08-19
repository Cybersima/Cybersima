from securetrade.engine.book import MarketBook
from securetrade.engine.capital import CapitalProtection
from securetrade.engine.consensus import PriceConsensus
from securetrade.engine.forced import make_quote
from securetrade.engine.guardian import Guardian
from securetrade.engine.scam import ScamDefense
from securetrade.engine.simulate import simulate_fill
from securetrade.engine.trust import TrustEngine
from securetrade.models import Leg, Opportunity, OpportunityKind


def _spectacular() -> Opportunity:
    return Opportunity(
        kind=OpportunityKind.CROSS_VENUE,
        edge_bps=900,
        net_edge_bps=874,
        notional=250,
        legs=[
            Leg("buy", "coinbase", "SCAMCOIN-USD", 0.01, True),
            Leg("sell", "kraken", "SCAMCOINUSD", 0.02, True),
        ],
        summary="Buy SCAMCOIN — 8.74% — honeypot",
        executable=True,
        ts=0,
        id="spectacular",
        pair="SCAMCOIN/USD",
        liquidity_usd=20,
        execution_confidence=0.99,
    )


def test_guardian_blocks_spectacular_insecure_edge() -> None:
    book = MarketBook()
    book.update(make_quote("coinbase", "SCAMCOIN-USD", 0.01, 0.011))
    book.update(make_quote("kraken", "SCAMCOINUSD", 0.02, 0.021))
    opp = _spectacular()
    consensus = PriceConsensus().evaluate(opp, book)
    scam = ScamDefense().inspect(opp)
    trust = TrustEngine().score(opp, consensus, scam)
    sim = simulate_fill(opp, book)
    verdict = Guardian().decide(opp, trust, consensus, scam, sim, "abnormal")
    assert verdict.allowed is False
    assert verdict.severity == "CRITICAL"
    assert scam.critical is True


def test_capital_never_overridden_by_confidence() -> None:
    capital = CapitalProtection({"max_trade_size": 50, "min_net_edge_bps": 8, "allowed_assets": ["BTC", "USD"], "allowed_exchanges": ["coinbase", "kraken"]})
    opp = Opportunity(
        kind=OpportunityKind.CROSS_VENUE,
        edge_bps=40,
        net_edge_bps=30,
        notional=250,
        legs=[Leg("buy", "coinbase", "BTC-USD", 1, True), Leg("sell", "kraken", "XBTUSD", 1, True)],
        summary="x",
        executable=True,
        ts=0,
        id="cap",
        pair="BTC/USD",
    )
    decision = capital.allow(opp, confidence=1.0)
    assert decision.allowed is False
    assert "trade size" in decision.reason
