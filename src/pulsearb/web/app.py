from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from pulsearb.branding import COMPANY, COPYRIGHT, PRODUCT, PRODUCT_SHORT, SIGNATURE
from pulsearb.engine.report import REPORT_HEADERS
from pulsearb.engine.runner import Engine, run_engine

WEB_DIR = Path(__file__).resolve().parent


def create_app(engine: Engine, start_engine: bool = False) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        task = None
        if start_engine:
            task = asyncio.create_task(run_engine(engine))
        yield
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title=PRODUCT, docs_url=None, redoc_url=None, lifespan=lifespan)
    templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "title": PRODUCT,
                "company": COMPANY,
                "product": PRODUCT,
                "product_short": PRODUCT_SHORT,
                "signature": SIGNATURE,
                "copyright": COPYRIGHT,
                "execution": (
                    f"live {'+'.join(engine.config.live_venue_names())}".strip()
                    if engine.config.live_enabled()
                    else "paper"
                ),
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

    @app.get("/api/report")
    async def report_json() -> dict:
        return {
            "headers": REPORT_HEADERS,
            "count": len(engine.report.rows),
            "rows": engine.report.as_dicts(),
        }

    @app.get("/api/report.csv")
    async def report_csv() -> Response:
        filename = "CyberSym-SecureTrade-profit-report.csv"
        return Response(
            content=engine.report.export_csv_bytes(),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )

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
