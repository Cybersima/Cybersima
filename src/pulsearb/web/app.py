from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from pulsearb.engine.runner import Engine

WEB_DIR = Path(__file__).resolve().parent


def create_app(engine: Engine) -> FastAPI:
    app = FastAPI(title="PulseArb", docs_url=None, redoc_url=None)
    templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "title": "PulseArb",
                "execution": "live" if engine.config.live_enabled() else "paper",
            },
        )

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True, "killed": engine.risk.killed}

    @app.get("/api/snapshot")
    async def snapshot() -> dict:
        return engine.snapshot()

    @app.post("/api/kill")
    async def kill() -> dict:
        engine.risk.kill()
        await engine.broadcast()
        return {"killed": True}

    @app.post("/api/resume")
    async def resume() -> dict:
        engine.risk.resume()
        await engine.broadcast()
        return {"killed": False}

    @app.websocket("/ws")
    async def ws_feed(ws: WebSocket) -> None:
        await ws.accept()
        queue = engine.subscribe()
        try:
            await ws.send_json(engine.snapshot())
            while True:
                payload = await queue.get()
                await ws.send_json(payload)
        except WebSocketDisconnect:
            pass
        finally:
            engine.unsubscribe(queue)

    return app
