import time

from pulsearb.engine.arbitrage import (
    detect_auto_cross,
    detect_cross_venue,
    detect_quote_dislocations,
    detect_triangles,
    discover_triangles,
)
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


def test_coinbase_vs_kraken_is_executable() -> None:
    book = MarketBook()
    book.update(make_quote("coinbase", "BTC-USD", 97000, 97010, executable=True))
    book.update(make_quote("kraken", "XBTUSD", 98100, 98120, executable=True))
    opps = detect_auto_cross(
        book,
        {"USD", "USDT", "USDC"},
        min_edge_bps=5,
        fee_bps_by_venue={"coinbase": 50, "kraken": 26},
        extra_slippage_bps=2,
        notional=250,
    )
    assert opps
    assert any(o.executable and o.kind is OpportunityKind.CROSS_VENUE for o in opps)


def test_coinbase_triangle_on_usd_book() -> None:
    book = MarketBook()
    book.update(make_quote("coinbase", "BTC-USD", 100000, 100010))
    book.update(make_quote("coinbase", "ETH-USD", 2000, 2001))
    book.update(make_quote("coinbase", "ETH-BTC", 0.01950, 0.01951))
    triangles = discover_triangles(["BTC-USD", "ETH-USD", "ETH-BTC"])
    opps = detect_triangles(
        book,
        triangles,
        min_edge_bps=20,
        taker_bps=10,
        extra_slippage_bps=0,
        notional=250,
        venue="coinbase",
    )
    assert opps
    assert max(opps, key=lambda o: o.net_edge_bps).net_edge_bps > 20


def test_triangle_watch_only_when_edge_is_below_take_threshold() -> None:
    book = MarketBook()
    book.update(make_quote("coinbase", "BTC-USD", 100000, 100010))
    book.update(make_quote("coinbase", "ETH-USD", 2000, 2001))
    book.update(make_quote("coinbase", "ETH-BTC", 0.01985, 0.01986))
    triangles = discover_triangles(["BTC-USD", "ETH-USD", "ETH-BTC"])
    opps = detect_triangles(
        book,
        triangles,
        min_edge_bps=8,
        taker_bps=10,
        extra_slippage_bps=0,
        notional=5,
        venue="coinbase",
        min_executable_edge_bps=80,
    )
    assert opps
    assert all(not row.executable for row in opps)


def test_coinbase_triangle_clears_retail_fees_on_two_and_a_half_percent() -> None:
    book = MarketBook()
    book.update(make_quote("coinbase", "BTC-USD", 100000, 100010))
    book.update(make_quote("coinbase", "ETH-USD", 2000, 2001))
    book.update(make_quote("coinbase", "ETH-BTC", 0.01950, 0.01951))
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
    assert best.net_edge_bps >= 25
    assert best.executable


def test_coinbase_usd_vs_usdc_dislocation_is_live_route() -> None:
    book = MarketBook()
    book.update(make_quote("coinbase", "BTC-USD", 97000, 97010, executable=True))
    book.update(make_quote("coinbase", "BTC-USDC", 98990, 99000, executable=True))
    book.update(make_quote("coinbase", "USDC-USD", 0.999, 1.001, executable=True))
    opps = detect_quote_dislocations(
        book,
        venue="coinbase",
        min_edge_bps=8,
        fee_map={"coinbase": 50, "coinbase_stable": 1.0},
        extra_slippage_bps=2,
        notional=10,
        min_executable_edge_bps=25,
    )
    assert opps
    best = max(opps, key=lambda o: o.net_edge_bps)
    assert best.kind is OpportunityKind.DISLOCATION
    assert best.executable
    assert best.legs[0].action == "buy"
    assert any(leg.symbol == "BTC-USDC" and leg.action == "sell" for leg in best.legs)


def test_kraken_fx_triangle_is_executable() -> None:
    book = MarketBook()
    book.update(make_quote("kraken", "EURUSD", 1.10, 1.1002, executable=True))
    book.update(make_quote("kraken", "GBPUSD", 1.26, 1.2602, executable=True))
    # Cheap EURGBP vs the USD legs so USD → EUR → GBP → USD can print after FX fees.
    book.update(make_quote("kraken", "EURGBP", 0.8600, 0.8601, executable=True))
    triangles = discover_triangles(["EUR-USD", "GBP-USD", "EUR-GBP"])
    assert ("EUR", "GBP", "USD") in triangles or ("EUR", "USD", "GBP") in triangles
    opps = detect_triangles(
        book,
        triangles,
        min_edge_bps=8,
        taker_bps=20,
        extra_slippage_bps=2,
        notional=10,
        venue="kraken",
        min_executable_edge_bps=25,
    )
    assert opps
    best = max(opps, key=lambda item: item.net_edge_bps)
    assert best.legs[0].action == "buy"
    assert best.summary.startswith("USD →")
    assert {leg.venue for leg in best.legs} == {"kraken"}


def test_triangle_only_starts_in_cash_and_buys_first() -> None:
    book = MarketBook()
    book.update(make_quote("kraken", "XBTUSD", 100000, 100010))
    book.update(make_quote("kraken", "LTCUSD", 80, 80.04))
    book.update(make_quote("kraken", "LTCXBT", 0.00078, 0.000781))
    triangles = discover_triangles(["XBTUSD", "LTCUSD", "LTCXBT"])
    opps = detect_triangles(
        book,
        triangles,
        min_edge_bps=8,
        taker_bps=26,
        extra_slippage_bps=2,
        notional=1,
        venue="kraken",
        min_executable_edge_bps=25,
    )
    assert opps
    for opp in opps:
        assert opp.legs[0].action == "buy"
        assert opp.summary.startswith("USD →")
        assert opp.legs[0].symbol.upper() != "XBTUSD" or opp.legs[0].action == "buy"
    ids = {opp.id for opp in opps}
    bumped = MarketBook()
    bumped.update(make_quote("kraken", "XBTUSD", 100000, 100010))
    bumped.update(make_quote("kraken", "LTCUSD", 80, 80.04))
    bumped.update(make_quote("kraken", "LTCXBT", 0.000778, 0.000779))
    again = detect_triangles(
        bumped,
        triangles,
        min_edge_bps=8,
        taker_bps=26,
        extra_slippage_bps=2,
        notional=1,
        venue="kraken",
        min_executable_edge_bps=25,
    )
    assert {opp.id for opp in again} & ids


def test_triangle_drops_fantasy_raw_edge() -> None:
    book = MarketBook()
    book.update(make_quote("coinbase", "BTC-USD", 100000, 100010))
    book.update(make_quote("coinbase", "ETH-USD", 2000, 2001))
    book.update(make_quote("coinbase", "ETH-BTC", 0.0170, 0.0171))
    triangles = discover_triangles(["BTC-USD", "ETH-USD", "ETH-BTC"])
    opps = detect_triangles(
        book,
        triangles,
        min_edge_bps=8,
        taker_bps=50,
        extra_slippage_bps=2,
        notional=1,
        venue="coinbase",
        min_executable_edge_bps=25,
        max_raw_edge_bps=300,
    )
    assert opps == []


def test_triangle_stale_quotes_are_watch_only() -> None:
    book = MarketBook()
    now = time.time()
    book.update(make_quote("coinbase", "BTC-USD", 100000, 100010))
    old = make_quote("coinbase", "ETH-USD", 2000, 2001)
    old.ts = now - 20
    book.update(old)
    book.update(make_quote("coinbase", "ETH-BTC", 0.01950, 0.01951))
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
        max_quote_age=8.0,
        max_quote_skew=1.5,
    )
    assert opps
    assert all(not opp.executable for opp in opps)


def test_dislocation_id_stable_and_fantasy_raw_dropped() -> None:
    book = MarketBook()
    book.update(make_quote("coinbase", "BTC-USD", 97000, 97010, executable=True))
    book.update(make_quote("coinbase", "BTC-USDC", 98990, 99000, executable=True))
    book.update(make_quote("coinbase", "USDC-USD", 0.999, 1.001, executable=True))
    kwargs = dict(
        venue="coinbase",
        min_edge_bps=8,
        fee_map={"coinbase": 50, "coinbase_stable": 1.0},
        extra_slippage_bps=2,
        notional=10,
        min_executable_edge_bps=25,
    )
    first = detect_quote_dislocations(book, **kwargs)
    book.update(make_quote("coinbase", "BTC-USDC", 98800, 98810, executable=True))
    second = detect_quote_dislocations(book, **kwargs)
    assert first and second
    assert {opp.id for opp in first} & {opp.id for opp in second}
    wild = MarketBook()
    wild.update(make_quote("coinbase", "BTC-USD", 97000, 97010, executable=True))
    wild.update(make_quote("coinbase", "BTC-USDC", 110000, 110010, executable=True))
    wild.update(make_quote("coinbase", "USDC-USD", 0.999, 1.001, executable=True))
    assert detect_quote_dislocations(wild, **kwargs) == []


def test_cross_venue_drops_fantasy_raw_edge() -> None:
    book = MarketBook()
    book.update(make_quote("coinbase", "BTC-USD", 97000, 97010, executable=True))
    book.update(make_quote("kraken", "XBTUSD", 110000, 110020, executable=True))
    opps = detect_auto_cross(
        book,
        {"USD", "USDT", "USDC"},
        min_edge_bps=5,
        fee_bps_by_venue={"coinbase": 50, "kraken": 26},
        extra_slippage_bps=2,
        notional=1,
        max_raw_edge_bps=300.0,
    )
    assert opps == []


def test_dislocation_take_floor_is_fifteen_not_twenty_five() -> None:
    book = MarketBook()
    book.update(make_quote("coinbase", "BTC-USD", 99990, 100000, executable=True))
    book.update(make_quote("coinbase", "BTC-USDC", 101080, 101090, executable=True))
    book.update(make_quote("coinbase", "USDC-USD", 0.999, 1.001, executable=True))
    kwargs = dict(
        venue="coinbase",
        min_edge_bps=8,
        fee_map={"coinbase": 50, "coinbase_maker": 40, "coinbase_stable": 1.0},
        extra_slippage_bps=2,
        notional=10,
    )
    at_fifteen = detect_quote_dislocations(book, **kwargs, min_executable_edge_bps=15)
    at_twenty_five = detect_quote_dislocations(book, **kwargs, min_executable_edge_bps=25)
    assert at_fifteen
    best = max(at_fifteen, key=lambda row: row.net_edge_bps)
    assert best.kind is OpportunityKind.DISLOCATION
    assert 15 <= best.net_edge_bps < 25
    assert best.executable
    assert at_twenty_five
    assert all(not row.executable for row in at_twenty_five)


def test_triangle_watch_only_between_dislocation_and_triangle_take_floors() -> None:
    book = MarketBook()
    book.update(make_quote("coinbase", "BTC-USD", 100000, 100010))
    book.update(make_quote("coinbase", "ETH-USD", 2000, 2001))
    book.update(make_quote("coinbase", "ETH-BTC", 0.01967, 0.01968))
    triangles = discover_triangles(["BTC-USD", "ETH-USD", "ETH-BTC"])
    kwargs = dict(
        min_edge_bps=8,
        taker_bps=50,
        extra_slippage_bps=2,
        notional=5,
        venue="coinbase",
        maker_bps=40,
    )
    watch = detect_triangles(book, triangles, **kwargs, min_executable_edge_bps=25)
    take = detect_triangles(book, triangles, **kwargs, min_executable_edge_bps=15)
    assert watch
    best = max(watch, key=lambda row: row.net_edge_bps)
    assert best.kind is OpportunityKind.TRIANGULAR
    assert 15 <= best.net_edge_bps < 25
    assert not best.executable
    assert take
    assert max(take, key=lambda row: row.net_edge_bps).executable


def test_cross_venue_paper_click_floor_is_twenty_five() -> None:
    thin = MarketBook()
    thin.update(make_quote("coinbase", "BTC-USD", 99990, 100000, executable=True))
    thin.update(make_quote("kraken", "XBTUSD", 100900, 100920, executable=True))
    kwargs = dict(
        usd_equivalents={"USD", "USDT", "USDC"},
        min_edge_bps=8,
        fee_bps_by_venue={"coinbase": 50, "kraken": 26},
        extra_slippage_bps=2,
        notional=10,
        min_executable_edge_bps=25,
    )
    thin_rows = detect_auto_cross(thin, **kwargs)
    assert thin_rows
    best_thin = max(thin_rows, key=lambda row: row.net_edge_bps)
    assert best_thin.kind is OpportunityKind.CROSS_VENUE
    assert 8 <= best_thin.net_edge_bps < 25
    assert not best_thin.executable

    fat = MarketBook()
    fat.update(make_quote("coinbase", "BTC-USD", 99990, 100000, executable=True))
    fat.update(make_quote("kraken", "XBTUSD", 101080, 101100, executable=True))
    fat_rows = detect_auto_cross(fat, **kwargs)
    assert fat_rows
    best_fat = max(fat_rows, key=lambda row: row.net_edge_bps)
    assert best_fat.kind is OpportunityKind.CROSS_VENUE
    assert best_fat.net_edge_bps >= 25
    assert best_fat.executable


