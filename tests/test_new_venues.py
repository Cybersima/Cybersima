from pulsearb.engine.money import auto_route_ok, live_exec_ok, oanda_roundtrip_ok, venue_live_ok
from pulsearb.engine.robinhood_live import LiveRobinhoodBroker
from pulsearb.engine.risk import RiskManager
from pulsearb.models import Leg, Opportunity, OpportunityKind


def _opp(*legs: tuple[str, str, str], executable: bool = True) -> Opportunity:
    return Opportunity(
        kind=OpportunityKind.TRIANGULAR,
        edge_bps=40,
        net_edge_bps=20,
        notional=5,
        legs=[Leg(action, venue, symbol, 1.0, True) for action, venue, symbol in legs],
        summary="test",
        executable=executable,
        ts=0,
        id="nv-1",
    )


def test_paper_auto_still_skips_gemini() -> None:
    gemini = _opp(("buy", "gemini", "BTC-USD"), ("sell", "gemini", "ETH-USD"), ("sell", "gemini", "ETH-BTC"))
    assert venue_live_ok(gemini, "gemini")
    assert not auto_route_ok(gemini, "coinbase", live=False)


def test_oanda_live_rejects_triangles() -> None:
    triangle = _opp(("buy", "oanda", "EUR-USD"), ("sell", "oanda", "EUR-GBP"), ("buy", "oanda", "GBP-USD"))
    assert venue_live_ok(triangle, "oanda")
    assert not oanda_roundtrip_ok(triangle)
    assert not live_exec_ok(triangle, "oanda")
    assert not auto_route_ok(triangle, "oanda", live=True)


def test_oanda_live_accepts_same_pair_roundtrip() -> None:
    pair = _opp(("buy", "oanda", "EUR-USD"), ("sell", "oanda", "EUR-USD"))
    assert oanda_roundtrip_ok(pair)
    assert live_exec_ok(pair, "oanda")


def test_robinhood_parse_ignores_requested_qty() -> None:
    broker = LiveRobinhoodBroker(RiskManager(), "k", "c2VjcmV0c2VjcmV0c2VjcmV0c2VjcmV0c2VjcmV0c2U=", None)
    state, qty, price, oid = broker._parse_order_result(
        {
            "id": "abc",
            "state": "open",
            "asset_quantity": "1.5",
            "quantity": "1.5",
            "price": "100",
        }
    )
    assert state == "open"
    assert qty == 0.0
    assert price == 0.0
    assert oid == "abc"
    state, qty, price, oid = broker._parse_order_result(
        {
            "id": "def",
            "state": "filled",
            "filled_asset_quantity": "0.01",
            "average_price": "100.5",
            "asset_quantity": "9",
        }
    )
    assert state == "filled"
    assert qty == 0.01
    assert price == 100.5


def test_risk_min_message_shows_cents() -> None:
    risk = RiskManager(min_notional_usdt=0.10)
    decision = risk.allow(0.05)
    assert decision.allowed is False
    assert "$0.10" in decision.reason
