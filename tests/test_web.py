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
    assert "Export report" in page.text
    assert 'id="live-banner"' in page.text
    assert 'id="guard-banner"' in page.text
    assert 'id="live-ready"' in page.text
    assert 'id="live-ready-refresh"' in page.text
    assert 'id="exec-paper"' in page.text
    assert 'id="exec-live"' in page.text
    assert "Paper or live" in page.text
    assert "Ready for live Coinbase" in page.text
    assert "logo.png" in page.text
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
    assert 'id="fills-meta"' in page.text
    assert "cybersym-theme" in page.text
    assert "I’ll pick each trade" in page.text or "I'll pick each trade" in page.text
    assert 'id="invest-amount"' in page.text
    desk = client.get("/api/desk")
    assert desk.status_code == 200
    assert desk.json()["auto_invest"] is False
    assert desk.json()["auto_allowed"] is True
    assert desk.json()["notional"] == 5
    assert desk.json()["min_notional"] == 1
    assert 1 in desk.json()["presets"]
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


def test_guard_pin_compare() -> None:
    guard = DashboardGuard()
    assert guard.pin_ok(guard.pin)
    assert not guard.pin_ok("999999")
    assert guard.token_ok(guard.unlock_token)
    assert not guard.token_ok("nope")
    assert not guard.cookie_ok("nope")
    assert guard.cookie_ok(guard.cookie)
