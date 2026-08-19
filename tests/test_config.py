from pulsearb.config import AppConfig
from pulsearb.engine.arbitrage import discover_triangles


def test_default_markets_cover_fifty_plus_us_venues() -> None:
    config = AppConfig()
    total = (
        len(config.symbols("coinbase"))
        + len(config.symbols("kraken"))
        + len(config.symbols("gemini"))
        + len(config.symbols("bitstamp"))
        + len(config.yahoo_symbols)
    )
    assert total >= 50
    assert config.venue_enabled("coinbase")
    assert config.venue_enabled("kraken")
    assert config.venue_enabled("gemini")
    assert config.venue_enabled("bitstamp")
    assert not config.venue_enabled("binance")


def test_triangles_discovered_from_coinbase_universe() -> None:
    config = AppConfig()
    triangles = discover_triangles(config.symbols("coinbase"))
    assert len(triangles) >= 1
    assert ("BTC", "ETH", "USD") in triangles or ("BTC", "USD", "ETH") in triangles
