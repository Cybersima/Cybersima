from pulsearb.engine.arbitrage import detect_triangles, discover_triangles
from pulsearb.engine.book import MarketBook
from pulsearb.feeds.simulator import SimulatorFeed


def test_simulator_triangle_shock_clears_coinbase_fees() -> None:
    feed = SimulatorFeed(
        instruments=[
            ("coinbase", "BTC-USD", True),
            ("coinbase", "ETH-USD", True),
            ("coinbase", "ETH-BTC", True),
        ]
    )
    feed._walk = lambda key: feed._mids[key]
    book = MarketBook()
    feed._tick(book, inject=True, triangle_shock=("ETH-BTC", "coinbase", 1.025), cross_shock=("skip", "none", 1.0))
    triangles = discover_triangles(["BTC-USD", "ETH-USD", "ETH-BTC"])
    opps = detect_triangles(
        book,
        triangles,
        min_edge_bps=8,
        taker_bps=50,
        extra_slippage_bps=2,
        notional=5,
        venue="coinbase",
        min_executable_edge_bps=25,
    )
    assert opps
    best = max(opps, key=lambda o: o.net_edge_bps)
    assert best.executable
    assert best.net_edge_bps >= 25
