from pulsearb.config import AppConfig
from pulsearb.engine.money import auto_route_ok, venue_live_ok
from pulsearb.engine.runner import Engine
from pulsearb.models import Leg, Opportunity, OpportunityKind


def _opp(
    *legs: tuple[str, str, str],
    kind: OpportunityKind = OpportunityKind.TRIANGULAR,
    oid: str = "auto-1",
    executable: bool = True,
    net: float = 40,
) -> Opportunity:
    return Opportunity(
        kind=kind,
        edge_bps=net + 20,
        net_edge_bps=net,
        notional=5,
        legs=[Leg(action, venue, symbol, 1.0, True) for action, venue, symbol in legs],
        summary="test",
        executable=executable,
        ts=0,
        id=oid,
    )


def kraken_usd_btc() -> Opportunity:
    return _opp(
        ("buy", "kraken", "XBTUSD"),
        ("sell", "kraken", "XBTUSDC"),
        ("sell", "kraken", "USDCUSD"),
        oid="kraken-usd-btc",
    )


def kraken_eth_usdc() -> Opportunity:
    return _opp(
        ("buy", "kraken", "ETHUSDC"),
        ("sell", "kraken", "ETHUSD"),
        oid="kraken-eth-usdc",
        kind=OpportunityKind.DISLOCATION,
    )


def kraken_gemini_btc() -> Opportunity:
    return _opp(
        ("buy", "kraken", "XBTUSD"),
        ("sell", "gemini", "BTC-USD"),
        oid="kraken-gemini-btc",
        kind=OpportunityKind.CROSS_VENUE,
        net=110,
    )


def coinbase_usd_btc() -> Opportunity:
    return _opp(
        ("buy", "coinbase", "BTC-USD"),
        ("sell", "coinbase", "BTC-USDC"),
        oid="cb-usd-btc",
        kind=OpportunityKind.DISLOCATION,
    )


def test_auto_route_ok_paper_takes_usd_start_same_venue() -> None:
    assert auto_route_ok(kraken_usd_btc(), "coinbase", live=False)
    assert auto_route_ok(coinbase_usd_btc(), "kraken", live=False)
    assert venue_live_ok(kraken_usd_btc(), "kraken")
    assert venue_live_ok(coinbase_usd_btc(), "coinbase")


def test_auto_route_ok_skips_cross_and_usdc_first() -> None:
    assert not auto_route_ok(kraken_gemini_btc(), "kraken", live=False)
    assert not auto_route_ok(kraken_eth_usdc(), "kraken", live=False)
    assert not venue_live_ok(kraken_eth_usdc(), "kraken")
    assert not venue_live_ok(kraken_gemini_btc(), "kraken")


def test_auto_route_ok_live_stays_on_selected_venue() -> None:
    assert auto_route_ok(kraken_usd_btc(), "kraken", live=True)
    assert not auto_route_ok(kraken_usd_btc(), "coinbase", live=True)
    assert not auto_route_ok(coinbase_usd_btc(), "kraken", live=True)
    assert auto_route_ok(coinbase_usd_btc(), "coinbase", live=True)


def test_paper_auto_candidates_drop_cross_and_usdc_first() -> None:
    engine = Engine(AppConfig())
    engine.desk.live_venue = "kraken"
    current = [kraken_gemini_btc(), kraken_eth_usdc(), kraken_usd_btc(), coinbase_usd_btc()]
    ids = {opp.id for opp in engine._auto_candidates(current)}
    assert ids == {"kraken-usd-btc", "cb-usd-btc"}


def test_paper_auto_idle_when_only_cross_venue() -> None:
    engine = Engine(AppConfig())
    engine.desk.auto_invest = True
    engine.opportunities.appendleft(kraken_gemini_btc())
    reason = engine._idle_reason()
    assert "Auto only takes" in reason
    assert "Cross-venue" in reason


def test_paper_click_still_investable_on_cross_venue() -> None:
    engine = Engine(AppConfig())
    opp = kraken_gemini_btc()
    view = engine._opp_view(opp)
    assert view["paper_only"] is True
    assert view["investable"] is True
    assert view["pending"] is False
    assert view["live_ok"] is False


def test_paper_usd_start_is_auto_pending() -> None:
    engine = Engine(AppConfig())
    engine.desk.auto_invest = True
    view = engine._opp_view(kraken_usd_btc())
    assert view["paper_only"] is False
    assert view["investable"] is False
    assert view["pending"] is True
    assert view["live_ok"] is True
