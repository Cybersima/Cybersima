from pulsearb.symbols import canonical_from_binance, split_binance_symbol


def test_split_known_quotes() -> None:
    assert split_binance_symbol("BTCUSDT") == ("BTC", "USDT")
    assert split_binance_symbol("ETHBTC") == ("ETH", "BTC")
    assert split_binance_symbol("BTCEUR") == ("BTC", "EUR")


def test_canonical() -> None:
    assert canonical_from_binance("solusdt") == "SOL-USDT"
