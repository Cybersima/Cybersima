from fastapi.testclient import TestClient

from pulsearb.config import AppConfig
from pulsearb.engine.runner import Engine
from pulsearb.web.app import create_app


def test_dashboard_and_kill_switch() -> None:
    engine = Engine(AppConfig())
    client = TestClient(create_app(engine))
    page = client.get("/")
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
    assert "logo.png" in page.text
    assert "I’ll pick each trade" in page.text or "I'll pick each trade" in page.text
    assert 'id="invest-amount"' in page.text
    desk = client.get("/api/desk")
    assert desk.status_code == 200
    assert desk.json()["auto_invest"] is False
    assert desk.json()["notional"] == 25
    updated = client.post("/api/desk", json={"notional": 50, "assets": ["BTC", "ETH"]})
    assert updated.status_code == 200
    assert updated.json()["notional"] == 50
    missed = client.post("/api/invest", json={"id": "missing"})
    assert missed.status_code == 200
    assert missed.json()["ok"] is False


def test_dashboard_serves_dropped_branding_logo(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "branding").mkdir()
    payload = b"\x89PNG\r\n\x1a\n" + b"official-crest"
    (tmp_path / "branding" / "cybersym-logo.png").write_bytes(payload)
    client = TestClient(create_app(Engine(AppConfig())))
    logo = client.get("/static/logo.png")
    assert logo.status_code == 200
    assert logo.content == payload
