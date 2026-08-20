from pulsearb.engine.trades import group_trades
from pulsearb.models import Fill


def _fill(**kwargs) -> Fill:
    base = dict(
        venue="coinbase",
        symbol="BTC-USD",
        side="buy",
        qty=0.0001,
        price=100000,
        notional=10,
        ts=1_700_000_000,
        paper=False,
        opportunity_id="tap-1",
        status="filled",
        note="order abc",
    )
    base.update(kwargs)
    return Fill(**base)


def test_group_trades_round_trip() -> None:
    fills = [
        _fill(side="sell", symbol="BTC-USD", qty=0.0001, price=100100, ts=1_700_000_002, note="flatten to USD · order z"),
        _fill(side="buy", symbol="ETH-BTC", qty=0.005, price=0.02, ts=1_700_000_001, note="order b"),
        _fill(side="buy", symbol="BTC-USD", qty=0.0001, price=100000, ts=1_700_000_000, note="order a"),
    ]
    trades = group_trades(fills)
    assert len(trades) == 1
    trade = trades[0]
    assert trade["execution"] == "live"
    assert trade["status"] == "closed"
    assert "sold leftover" in trade["close_label"].lower() or "sold back" in trade["close_label"].lower()
    assert trade["spent_usd"] == 10
    assert len(trade["legs"]) == 3
    assert trade["legs"][0]["side"] == "buy"
    assert trade["legs"][-1]["flatten"] is True
