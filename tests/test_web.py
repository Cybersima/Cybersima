from fastapi.testclient import TestClient

from pulsearb.config import AppConfig
from pulsearb.engine.runner import Engine
from pulsearb.web.app import create_app


def test_dashboard_and_kill_switch() -> None:
    engine = Engine(AppConfig())
    client = TestClient(create_app(engine))
    page = client.get("/")
    assert page.status_code == 200
    assert "PulseArb" in page.text
    assert client.get("/api/health").json() == {"ok": True, "killed": False}
    assert client.post("/api/kill").json() == {"killed": True}
    assert client.get("/api/health").json()["killed"] is True
    assert client.post("/api/resume").json() == {"killed": False}
    css = client.get("/static/app.css")
    assert css.status_code == 200
    assert "--gold" in css.text
