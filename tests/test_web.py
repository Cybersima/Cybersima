from fastapi.testclient import TestClient

from securetrade.config import AppConfig
from securetrade.engine.runner import Engine
from securetrade.web.app import create_app


def test_dashboard_and_kill_switch() -> None:
    engine = Engine(AppConfig())
    client = TestClient(create_app(engine))
    page = client.get("/")
    assert page.status_code == 200
    assert "CyberSym SecureTrade" in page.text
    assert "A CyberSym product" in page.text
    assert "Why this trade?" in page.text
    assert "Expected profit" in page.text
    starter = client.get("/api/starter").json()
    assert starter["rung"] == "learn_100"
    assert {row["id"] for row in starter["ladder"]} == {"learn_10", "learn_100", "paper_100", "live_100"}
    switched = client.post("/api/starter", json={"rung": "learn_10"}).json()
    assert switched["equity"] == 10
    blocked_auto = client.post("/api/mode", json={"mode": "auto"}).json()
    assert blocked_auto["ok"] is False
    health = client.get("/api/health").json()
    assert health["ok"] is True
    assert health["killed"] is False
    killed = client.post("/api/kill").json()
    assert killed["killed"] is True
    assert client.get("/api/health").json()["killed"] is True
    resumed = client.post("/api/resume").json()
    assert resumed["killed"] is False
    css = client.get("/static/app.css")
    assert css.status_code == 200
    assert "--gold" in css.text
    assert "--up" in css.text  # CAPTURED green
    assert ".tick.profit" in css.text
    assert ".tick.loss" in css.text
    assert ".tick.missed" in css.text
    assert ".tick.reversal" in css.text
    assert "Green profit" in page.text
    assert "Orange reversal" in page.text
    assert "Export profit report" in page.text
    assert "Export Excel" in page.text
    assert "Export CSV" in page.text
    assert "/api/profit-report.xlsx" in page.text
    assert f"/static/app.css?v=" in page.text
    assert f"/static/app.js?v=" in page.text
    assert "no-store" in page.headers.get("cache-control", "")
    state = client.get("/api/state")
    assert state.status_code == 200
    assert "stats" in state.json()
    assert "quotes" in state.json()
    snap = client.get("/api/snapshot").json()
    assert snap["stats"]["edition"] == state.json()["stats"]["edition"]
    report = client.get("/api/profit-report").json()
    assert report["headers"][0] == "ID"
    assert "Market" in report["headers"]
    assert report["headers"][-1] == "Paper Notional"
    xlsx = client.get("/api/profit-report.xlsx")
    assert xlsx.status_code == 200
    assert "spreadsheetml" in xlsx.headers["content-type"]
    csv_file = client.get("/api/profit-report.csv")
    assert csv_file.status_code == 200
    assert csv_file.text.splitlines()[0].startswith("ID,Detected Time,Strategy,Market")
    commit = client.get("/api/recovery-commit").json()
    assert "ATOMIC_READY" in commit["pipeline"]
    academy = client.get("/api/academy").json()
    assert len(academy["lessons"]) >= 8
    assert client.get("/api/updates").json()["require_signature"] is True
