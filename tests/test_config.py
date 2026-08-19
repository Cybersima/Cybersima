from securetrade.config import AppConfig
from securetrade.engine.arbitrage import discover_triangles


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
    assert config.execution_mode == "paper"
    assert config.starting_equity == 100
    assert config.ticket_size == 100
    assert config.starter_rung == "learn_100"


def test_triangles_discovered_from_coinbase_universe() -> None:
    config = AppConfig()
    triangles = discover_triangles(config.symbols("coinbase"))
    assert len(triangles) >= 1
    assert ("BTC", "ETH", "USD") in triangles or ("BTC", "USD", "ETH") in triangles


def test_live_stays_locked_without_safety_checks() -> None:
    config = AppConfig()
    config.settings["execution"]["mode"] = "live"
    assert config.live_enabled() is False
    gates = config.live_prerequisites()
    assert gates["paper_is_default"] is False
    assert gates["live_confirm"] is False
