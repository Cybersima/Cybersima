from pulsearb.config import AppConfig
from pulsearb.engine.arbitrage import discover_triangles


def test_default_markets_cover_fifty_plus_us_venues() -> None:
    config = AppConfig()
    total = (
        len(config.symbols("coinbase"))
        + len(config.symbols("kraken"))
        + len(config.symbols("gemini"))
        + len(config.symbols("oanda"))
        + len(config.symbols("robinhood"))
    )
    assert total >= 50
    assert config.venue_enabled("coinbase")
    assert config.venue_enabled("kraken")
    assert config.venue_enabled("gemini")
    assert config.venue_enabled("oanda")
    assert config.venue_enabled("robinhood")
    assert not config.venue_enabled("bitstamp")
    assert config.venue_enabled("yahoo")
    assert not config.venue_enabled("binance")
    assert config.fee_map()["robinhood"] == 85.0


def test_triangles_discovered_from_coinbase_universe() -> None:
    config = AppConfig()
    triangles = discover_triangles(config.symbols("coinbase"))
    assert len(triangles) >= 1
    assert ("BTC", "ETH", "USD") in triangles or ("BTC", "USD", "ETH") in triangles


def test_kraken_universe_includes_live_fx_triangle() -> None:
    config = AppConfig()
    symbols = config.symbols("kraken")
    assert "EUR-USD" in symbols
    assert "GBP-USD" in symbols
    assert "EUR-GBP" in symbols
    triangles = discover_triangles(symbols)
    assert ("EUR", "GBP", "USD") in triangles or ("EUR", "USD", "GBP") in triangles
    assert config.fee_map()["kraken_fx"] == 20.0
    assert config.fee_map()["kraken_maker"] == 16.0
    assert config.maker_exits() is True


def test_strategy_edge_defaults_split_take_floors() -> None:
    config = AppConfig()
    show, take = config.strategy_edge("dislocation")
    assert show == 8.0
    assert take == 15.0
    show, take = config.strategy_edge("triangular")
    assert show == 8.0
    assert take == 25.0
    show, take = config.strategy_edge("cross_venue")
    assert show == 8.0
    assert take == 25.0
    show, take = config.strategy_edge("triangle")
    assert take == 25.0
    show, take = config.strategy_edge("unknown")
    assert show == 8.0
    assert take == 15.0
