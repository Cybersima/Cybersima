import json

from fastapi.testclient import TestClient

from pulsearb.config import AppConfig
from pulsearb.engine.runner import Engine
from pulsearb.web.app import create_app
from pulsearb.web.guard import DashboardGuard


def open_dashboard(engine: Engine | None = None):
    engine = engine or Engine(AppConfig())
    app = create_app(engine)
    client = TestClient(app)
    token = app.state.guard.unlock_token
    page = client.get(f"/?unlock={token}", follow_redirects=True)
    return client, engine, app, page


def test_dashboard_and_kill_switch() -> None:
    client, engine, app, page = open_dashboard()
    assert page.status_code == 200
    assert "CyberSym SecureTrade" in page.text
    assert "A CyberSym product" in page.text
    assert "SecureTrade" in page.text
    assert client.get("/api/health").json() == {"ok": True, "killed": False}
    assert client.post("/api/kill").json() == {"killed": True}
    assert client.get("/api/health").json()["killed"] is True
    assert client.post("/api/resume").json() == {"killed": False}
    css = client.get("/static/app.css")
    assert css.status_code == 200
    assert "--cyan" in css.text
    assert "--gold" in css.text
    assert 'html[data-theme="light"]' in css.text
    assert "--input" in css.text
    assert ".live-ready" in css.text
    logo = client.get("/static/logo.png")
    assert logo.status_code == 200
    assert logo.headers["content-type"].startswith("image/")
    assert "logo.png" in page.text or "/brand/logo" in page.text
    report = client.get("/api/report")
    assert report.status_code == 200
    assert report.json()["headers"][0] == "ID"
    csv_file = client.get("/api/report.csv")
    assert csv_file.status_code == 200
    assert csv_file.headers["content-type"].startswith("application/octet-stream")
    assert "CyberSym-SecureTrade-profit-report.csv" in csv_file.headers["content-disposition"]
    assert csv_file.content.startswith(b"\xef\xbb\xbf")
    assert b"Detected Time" in csv_file.content
    assert b"Paper Notional" in csv_file.content
    assert 'id="export-report"' in page.text
    assert "Export my trades" in page.text
    assert 'id="cash-bar"' in page.text
    assert 'id="reference-grid"' in page.text
    assert "Yahoo reference" in page.text
    assert "Your trades" in page.text
    assert 'id="live-banner"' in page.text
    assert 'id="phone-dock"' in page.text
    assert 'id="phone-install"' in page.text
    assert "/manifest.json" in page.text
    assert 'id="block-banner"' in page.text
    assert 'id="guard-banner"' in page.text
    assert 'id="live-ready"' in page.text
    assert 'id="live-ready-refresh"' in page.text
    assert 'id="exec-paper"' in page.text
    assert 'id="exec-live"' in page.text
    assert "Paper or live" in page.text
    assert "Ready for live trading" in page.text
    assert 'id="live-venue-chips"' in page.text
    assert 'id="sched-start"' in page.text
    assert "Only between" in page.text
    assert "/brand/logo" in page.text
    assert 'id="theme-dark"' in page.text
    assert 'id="theme-light"' in page.text
    assert 'id="sound-on"' in page.text
    assert 'id="sound-off"' in page.text
    assert "Trade alert sound" in page.text
    js = client.get("/static/app.js")
    assert js.status_code == 200
    assert "cybersym-sound" in js.text
    assert "playChime" in js.text
    assert "noticeNewFills" in js.text
    assert "Trade complete" in js.text
    assert "paintLiveReady" in js.text
    assert "auto_allowed" in js.text
    assert "emptyOppsMessage" in js.text
    assert "three Coinbase fees" in js.text
    assert "USD vs USDC dislocations" in page.text
    assert "Kraken FX" in page.text
    assert "maker" in page.text.lower()
    assert "Yahoo" in page.text and "Bitstamp" in page.text
    assert "asset_class === \"fx\"" in js.text or 'asset_class === "fx"' in js.text
    assert "tradeCard" in js.text
    assert "cash-usd" in js.text
    assert "idle_reason" in js.text
    assert "usd_spendable" in js.text
    assert "setupPhoneShell" in js.text
    assert "paintPhonePair" in js.text
    assert "reference_quotes" in js.text
    assert "cybersym-theme" in page.text
    assert "I’ll pick each trade" in page.text or "I'll pick each trade" in page.text
    assert 'id="invest-amount"' in page.text
    desk = client.get("/api/desk")
    assert desk.status_code == 200
    assert desk.json()["auto_invest"] is False
    assert desk.json()["auto_allowed"] is True
    assert desk.json()["notional"] == 5
    assert desk.json()["min_notional"] == 0.1
    assert 1 in desk.json()["presets"]
    assert 0.1 in desk.json()["presets"]
    ids = {row["id"] for row in desk.json()["venue_choices"]}
    assert "yahoo" not in ids
    assert "bitstamp" not in ids
    assert "robinhood" in ids
    assert "oanda" in ids
    updated = client.post("/api/desk", json={"notional": 50, "assets": ["BTC", "ETH"]})
    assert updated.status_code == 200
    assert updated.json()["notional"] == 50
    missed = client.post("/api/invest", json={"id": "missing"})
    assert missed.status_code == 200
    assert missed.json()["ok"] is False
    status = client.get("/api/security").json()
    assert status["ok"] is True
    assert status["lock"] == "on"
    assert status["execution"] == "paper"
    ready = client.get("/api/live-ready")
    assert ready.status_code == 200
    body = ready.json()
    assert body["ok"] is True
    assert body["ready"] is False
    assert client.post("/api/execution", json={"mode": "paper"}).json()["ok"] is True
    live_try = client.post("/api/execution", json={"mode": "live"})
    assert live_try.status_code == 200
    assert live_try.json()["ok"] is False


def test_yahoo_quotes_are_reference_not_markets() -> None:
    from tests.helpers import make_quote

    client, engine, _, page = open_dashboard()
    engine.book.update(make_quote("yahoo", "EUR-USD", 1.1, 1.101, executable=True))
    engine.book.update(make_quote("coinbase", "BTC-USD", 100000, 100010, executable=True))
    snap = client.get("/api/snapshot").json()
    assert all(row["venue"] != "yahoo" for row in snap["quotes"])
    assert any(row["venue"] == "coinbase" for row in snap["quotes"])
    refs = snap.get("reference_quotes") or []
    assert any(row["venue"] == "yahoo" for row in refs)
    assert all(row["executable"] is False for row in refs if row["venue"] == "yahoo")
    assert "Yahoo reference" in page.text


def test_clear_boards_wipes_tapes_independently() -> None:
    client, engine, _, page = open_dashboard()
    assert 'id="clear-opps"' in page.text
    assert 'id="clear-fills"' in page.text
    assert "PAPER or LIVE" in page.text
    js = client.get("/static/app.js")
    assert "/api/clear" in js.text
    css = client.get("/static/app.css")
    assert ".clear-btn" in css.text

    from pulsearb.models import Fill, Leg, Opportunity, OpportunityKind

    opp = Opportunity(
        kind=OpportunityKind.TRIANGULAR,
        edge_bps=40,
        net_edge_bps=28,
        notional=5,
        legs=[
            Leg("buy", "kraken", "XBTUSD", 97000, True),
            Leg("sell", "kraken", "XBTUSDC", 98100, True),
        ],
        summary="test",
        executable=True,
        ts=0,
        id="clear-1",
    )
    engine.opportunities.appendleft(opp)
    engine.seen.add(opp.id)
    engine.by_id[opp.id] = opp
    engine.stats.opportunities = 1
    engine.fills.appendleft(
        Fill(
            venue="kraken",
            symbol="XBTUSD",
            side="buy",
            qty=0.001,
            price=97000,
            notional=5,
            ts=1,
            paper=True,
            opportunity_id="clear-1",
            status="filled",
            note="paper fill",
        )
    )
    engine.paper.pnl = 12.5
    engine.invested.add("clear-1")

    only_opps = client.post("/api/clear", json={"opportunities": True, "fills": False})
    assert only_opps.json() == {"ok": True, "opportunities": True, "fills": False}
    snap = client.get("/api/snapshot").json()
    assert snap["opportunities"] == []
    assert snap["fills"]
    assert engine.paper.pnl == 12.5

    wiped = client.post("/api/clear", json={"opportunities": False, "fills": True})
    assert wiped.json() == {"ok": True, "opportunities": False, "fills": True}
    snap = client.get("/api/snapshot").json()
    assert snap["fills"] == []
    assert snap["trades"] == []
    assert engine.paper.pnl == 0
    assert engine.invested == set()
    assert engine.report.taken_rows == 0


def test_dashboard_requires_lock_without_session() -> None:
    app = create_app(Engine(AppConfig()))
    client = TestClient(app, follow_redirects=False)
    locked = client.get("/")
    assert locked.status_code in {303, 307}
    assert "/login" in locked.headers.get("location", "")
    deny = client.post("/api/kill")
    assert deny.status_code == 401
    login = client.get("/login")
    assert login.status_code == 200
    assert "lock PIN" in login.text
    assert "/manifest.json" in login.text
    assert "apple-mobile-web-app-capable" in login.text
    assert "/brand/logo" in login.text
    bad = client.post("/api/unlock", json={"pin": "000000"})
    assert bad.json()["ok"] is False
    good = client.post("/api/unlock", json={"pin": app.state.guard.pin})
    assert good.json() == {"ok": True}
    assert client.get("/").status_code == 200


def test_dashboard_serves_dropped_branding_logo(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "branding").mkdir()
    payload = b"\x89PNG\r\n\x1a\n" + b"official-crest"
    (tmp_path / "branding" / "cybersym-logo.png").write_bytes(payload)
    client, _, _, _ = open_dashboard()
    logo = client.get("/static/logo.png")
    assert logo.status_code == 200
    assert logo.content == payload
    brand = client.get("/brand/logo")
    assert brand.status_code == 200
    assert brand.content == payload
    assert "no-store" in brand.headers.get("cache-control", "")
    page = client.get("/")
    assert "/brand/logo?v=" in page.text



def test_guard_pin_compare() -> None:
    guard = DashboardGuard()
    assert guard.pin_ok(guard.pin)
    assert not guard.pin_ok("999999")
    assert guard.token_ok(guard.unlock_token)
    assert not guard.token_ok("nope")
    assert not guard.cookie_ok("nope")
    assert guard.cookie_ok(guard.cookie)


def test_phone_app_shell_is_public_and_pairable() -> None:
    app = create_app(Engine(AppConfig()))
    locked = TestClient(app, follow_redirects=False)
    sw = locked.get("/sw.js")
    assert sw.status_code == 200
    assert "cybersym-securetrade-shell" in sw.text
    assert sw.headers.get("service-worker-allowed") == "/"
    manifest = locked.get("/manifest.json")
    assert manifest.status_code == 200
    body = json.loads(manifest.text)
    assert body["display"] == "standalone"
    assert body["short_name"] == "SecureTrade"
    phone = locked.get("/api/phone")
    assert phone.status_code == 401

    client, engine, _, page = open_dashboard()
    assert 'id="phone-dock"' in page.text
    assert "Add to Home Screen" in page.text
    css = client.get("/static/app.css")
    assert ".phone-dock" in css.text
    pair = client.get("/api/phone")
    assert pair.status_code == 200
    data = pair.json()
    assert data["ok"] is True
    assert "pin_hint" in data
    assert data["local"].startswith("http://127.0.0.1:")
    engine.config.settings["host"] = "0.0.0.0"
    engine.config.settings["port"] = 8080
    open_lan = client.get("/api/phone").json()
    assert open_lan["lan"] is True
    assert isinstance(open_lan["urls"], list)

