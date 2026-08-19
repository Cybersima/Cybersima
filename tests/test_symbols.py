from securetrade.symbols import (
    canonical_from_pair,
    comparison_key,
    split_binance_symbol,
    split_pair,
    to_native_symbol,
)


def test_split_known_quotes() -> None:
    assert split_binance_symbol("BTCUSDT") == ("BTC", "USDT")
    assert split_binance_symbol("ETHBTC") == ("ETH", "BTC")
    assert split_binance_symbol("BTCEUR") == ("BTC", "EUR")
    assert split_pair("BTC-USD") == ("BTC", "USD")
    assert split_pair("ETH/BTC") == ("ETH", "BTC")
    assert split_pair("XBTUSD") == ("BTC", "USD")


def test_canonical() -> None:
    assert canonical_from_pair("solusdt") == "SOL-USDT"
    assert canonical_from_pair("BTC-USD") == "BTC-USD"


def test_native_symbols() -> None:
    assert to_native_symbol("coinbase", "BTC-USD") == "BTC-USD"
    assert to_native_symbol("kraken", "BTC-USD") == "XBTUSD"
    assert to_native_symbol("kraken", "ETH-BTC") == "ETHXBT"
    assert to_native_symbol("gemini", "BTC-USD") == "btcusd"
    assert to_native_symbol("bitstamp", "ETH-BTC") == "ethbtc"


def test_usd_comparison_key_treats_usdt_as_usd() -> None:
    assert comparison_key("BTC-USDT") == "BTC-USD"
    assert comparison_key("BTC-USD") == "BTC-USD"
    assert comparison_key("ETH-BTC") == "ETH-BTC"
