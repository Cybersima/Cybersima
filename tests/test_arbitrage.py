from pulsearb.engine.arbitrage import detect_cross_venue, detect_triangles, discover_triangles
from pulsearb.engine.book import MarketBook
from pulsearb.models import OpportunityKind
from tests.helpers import make_quote, seeded_book


def test_convert_round_trip_loses_on_spread() -> None:
    book = seeded_book()
    btc = book.convert("USDT", "BTC", 100010)
    assert btc is not None
    assert abs(btc - 1.0) < 1e-9
    usdt = book.convert("BTC", "USDT", 1.0)
    assert usdt is not None
    assert usdt < 100010


def test_triangle_detects_mispriced_ethbtc() -> None:
    book = seeded_book()
    triangles = discover_triangles(["BTCUSDT", "ETHUSDT", "ETHBTC"])
    assert ("BTC", "ETH", "USDT") in triangles or ("BTC", "USDT", "ETH") in triangles
    opps = detect_triangles(book, triangles, min_edge_bps=20, taker_bps=10, extra_slippage_bps=0, notional=250)
    assert opps
    best = max(opps, key=lambda o: o.net_edge_bps)
    assert best.kind is OpportunityKind.TRIANGULAR
    assert best.executable
    assert best.net_edge_bps > 20


def test_cross_venue_yahoo_is_alert_only() -> None:
    book = MarketBook()
    book.update(make_quote("binance", "BTCUSDT", 97000, 97010, executable=True))
    book.update(make_quote("yahoo", "BTC-USD", 98100, 98120, executable=False))
    pairs = [
        {
            "id": "btc-usd",
            "left": {"venue": "binance", "symbol": "BTCUSDT"},
            "right": {"venue": "yahoo", "symbol": "BTC-USD"},
        }
    ]
    opps = detect_cross_venue(
        book,
        pairs,
        min_edge_bps=5,
        fee_bps_by_venue={"binance": 10, "yahoo": 0},
        extra_slippage_bps=2,
        notional=250,
    )
    assert opps
    assert all(not o.executable for o in opps)
    assert all(o.kind is OpportunityKind.ALERT for o in opps)


def test_no_cross_when_inside_fees() -> None:
    book = MarketBook()
    book.update(make_quote("binance", "BTCUSDT", 100000, 100010, True))
    book.update(make_quote("yahoo", "BTC-USD", 100000, 100020, False))
    pairs = [
        {
            "id": "btc-usd",
            "left": {"venue": "binance", "symbol": "BTCUSDT"},
            "right": {"venue": "yahoo", "symbol": "BTC-USD"},
        }
    ]
    opps = detect_cross_venue(
        book,
        pairs,
        min_edge_bps=8,
        fee_bps_by_venue={"binance": 10, "yahoo": 0},
        extra_slippage_bps=2,
        notional=250,
    )
    assert opps == []
