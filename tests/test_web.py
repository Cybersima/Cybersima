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
    assert "Guardian" in page.text
    assert "Forex Desk" in page.text
    assert "30s" in page.text
    assert "/download" in page.text
    download = client.get("/download")
    assert download.status_code == 200
    assert "Download for Windows" in download.text
    listed = client.get("/api/downloads").json()
    assert listed["filename"].endswith(".zip")
    assert listed["version"]
    fx = client.get("/api/forex").json()
    assert fx["poll_seconds"] == 3.0
    assert "1d" in fx["timeframes"]
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
    assert ".captured" in css.text
    assert ".reversed" in css.text
    assert ".missed" in css.text
    commit = client.get("/api/recovery-commit").json()
    assert "ATOMIC_READY" in commit["pipeline"]
    academy = client.get("/api/academy").json()
    assert len(academy["lessons"]) >= 8
    assert client.get("/api/updates").json()["require_signature"] is True
