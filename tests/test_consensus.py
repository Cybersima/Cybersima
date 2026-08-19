from securetrade.engine.consensus import PriceConsensus
from securetrade.engine.forced import make_quote
from securetrade.engine.book import MarketBook
from securetrade.models import Leg, Opportunity, OpportunityKind


def test_consensus_quarantines_outlier_feed() -> None:
    book = MarketBook()
    book.update(make_quote("coinbase", "BTC-USD", 97000, 97010))
    book.update(make_quote("kraken", "XBTUSD", 97100, 97120))
    book.update(make_quote("gemini", "btcusd", 120000, 120100))
    opp = Opportunity(
        kind=OpportunityKind.CROSS_VENUE,
        edge_bps=20,
        net_edge_bps=10,
        notional=250,
        legs=[
            Leg("buy", "coinbase", "BTC-USD", 97010, True),
            Leg("sell", "kraken", "XBTUSD", 97100, True),
        ],
        summary="btc",
        executable=True,
        ts=0,
        id="c",
        pair="BTC-USD",
    )
    result = PriceConsensus(outlier_bps=80).evaluate(opp, book)
    assert "gemini" in result.outlier_venues
    assert result.sources >= 2
