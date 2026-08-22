from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse

from pulsearb.branding import COMPANY, COPYRIGHT, PRODUCT, PRODUCT_SHORT, SIGNATURE, resolve_logo_path
from pulsearb.engine.report import REPORT_HEADERS
from pulsearb.engine.runner import Engine, run_engine
from pulsearb.web.guard import COOKIE, DashboardGuard

WEB_DIR = Path(__file__).resolve().parent
OPEN_PATHS = {"/login", "/api/unlock"}


class GuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        guard: DashboardGuard = request.app.state.guard
        path = request.url.path
        if path.startswith("/static/") or path in OPEN_PATHS:
            return await call_next(request)
        token = request.query_params.get("unlock")
        if token and guard.token_ok(token):
            response = RedirectResponse(url="/", status_code=303)
            response.set_cookie(COOKIE, guard.cookie, httponly=True, samesite="lax", path="/")
            return response
        if guard.cookie_ok(request.cookies.get(COOKIE)):
            return await call_next(request)
        if path.startswith("/api/"):
            return JSONResponse(
                {"ok": False, "error": "Dashboard is locked. Enter the PIN from the black window."},
                status_code=401,
            )
        return RedirectResponse(url="/login", status_code=303)


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
    app.state.guard = DashboardGuard()
    engine.guard = app.state.guard
    templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))
    app.add_middleware(GuardMiddleware)

    def _set_session(response: Response) -> None:
        response.set_cookie(COOKIE, app.state.guard.cookie, httponly=True, samesite="lax", path="/")

    @app.get("/static/logo.png")
    async def branded_logo() -> FileResponse:
        path = resolve_logo_path(WEB_DIR)
        suffix = path.suffix.lower()
        media = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(suffix, "image/png")
        return FileResponse(path, media_type=media, headers={"Cache-Control": "no-store"})

    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    @app.get("/login", response_class=HTMLResponse)
    async def login(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "company": COMPANY,
                "product": PRODUCT,
                "product_short": PRODUCT_SHORT,
            },
        )

    @app.post("/api/unlock")
    async def unlock(payload: dict, response: Response) -> dict:
        guard: DashboardGuard = app.state.guard
        if guard.locked_out():
            return {"ok": False, "error": "Too many tries. Wait 20 seconds, then use the PIN from the black window."}
        if not guard.pin_ok(str(payload.get("pin") or "")):
            return {"ok": False, "error": "That PIN does not match the black window."}
        _set_session(response)
        return {"ok": True}

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
                    if engine.live_active()
                    else "paper"
                ),
            },
        )

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True, "killed": engine.risk.killed}

    @app.get("/api/live-ready")
    async def live_ready() -> dict:
        from pulsearb.engine.live_ready import assess_live_ready

        return await assess_live_ready(
            engine.config,
            killed=engine.risk.killed,
            armed=engine.live_active(),
            venue=engine.desk.live_venue,
        )

    @app.get("/api/security")
    async def security() -> dict:
        host = engine.config.host
        local = host in {"127.0.0.1", "localhost", "::1"}
        keys = (Path.cwd() / "keys" / "coinbase.json").is_file() or (Path.cwd() / "keys" / "kraken.json").is_file()
        return {
            "ok": True,
            "lock": "on",
            "network": "this-computer" if local else "lan",
            "network_note": (
                "Dashboard is only on this computer."
                if local
                else "Dashboard is on your Wi-Fi. Anyone needs the PIN."
            ),
            "execution": "live" if engine.live_active() else "paper",
            "live_cap": engine.config.live_notional() if engine.live_active() else engine.desk.notional,
            "keys_file": keys,
            "killed": engine.risk.killed,
            "note": "API keys stay in keys\\coinbase.json or keys\\kraken.json on this PC. Never paste them into the dashboard.",
        }

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

    @app.get("/api/desk")
    async def get_desk() -> dict:
        return engine.desk_view()

    @app.post("/api/desk")
    async def update_desk(payload: dict) -> dict:
        desk = engine.apply_desk(payload)
        await engine.broadcast()
        return desk

    @app.post("/api/execution")
    async def set_execution(payload: dict) -> dict:
        result = await engine.set_execution(str(payload.get("mode") or ""), str(payload.get("confirm") or ""))
        return result

    @app.post("/api/invest")
    async def invest(payload: dict) -> dict:
        result = await engine.invest(str(payload.get("id") or ""))
        return result

    @app.post("/api/clear")
    async def clear_boards(payload: dict | None = None) -> dict:
        body = payload or {}
        opportunities = True if "opportunities" not in body else bool(body.get("opportunities"))
        fills = True if "fills" not in body else bool(body.get("fills"))
        result = engine.clear_boards(opportunities=opportunities, fills=fills)
        await engine.broadcast()
        return result

    @app.get("/api/report")
    async def report_json() -> dict:
        return {
            "headers": REPORT_HEADERS,
            "count": engine.report.taken_rows,
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
        guard: DashboardGuard = app.state.guard
        if not guard.cookie_ok(ws.cookies.get(COOKIE)):
            await ws.close(code=4401)
            return
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
