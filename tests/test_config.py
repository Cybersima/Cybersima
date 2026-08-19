from pulsearb.config import AppConfig
from pulsearb.engine.arbitrage import discover_triangles


def test_default_markets_cover_fifty_plus() -> None:
    config = AppConfig()
    total = len(config.binance_symbols) + len(config.yahoo_symbols)
    assert total >= 50
    assert len(config.binance_symbols) >= 50


def test_triangles_discovered_from_default_universe() -> None:
    config = AppConfig()
    triangles = discover_triangles(config.binance_symbols)
    assert len(triangles) >= 1
