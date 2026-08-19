from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.requests import Request

from securetrade.academy import LESSONS, explain_rejection
from securetrade.branding import (
    COMPANY,
    COPYRIGHT,
    GUARDIAN_NAME,
    PRODUCT,
    PRODUCT_SHORT,
    SIGNATURE,
    TAGLINE,
    VERSION,
)
from securetrade.engine.runner import Engine, run_engine
from securetrade.models import KillSource, OperatingMode
from securetrade.updates import check_for_updates
from securetrade.wizard import STEPS, mark_complete, needs_wizard


WEB_DIR = Path(__file__).resolve().parent


class ModeBody(BaseModel):
    mode: str


class ApproveBody(BaseModel):
    opportunity_id: str


class ReauthBody(BaseModel):
    device_id: str = "command-center"
    ip: str = "127.0.0.1"
    geo: str = "local"


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

    def page(request: Request, name: str = "index.html") -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            name,
            {
                "title": PRODUCT,
                "company": COMPANY,
                "product": PRODUCT,
                "product_short": PRODUCT_SHORT,
                "signature": SIGNATURE,
                "copyright": COPYRIGHT,
                "tagline": TAGLINE,
                "version": VERSION,
                "guardian": GUARDIAN_NAME,
                "execution": "live" if engine.config.live_enabled() else "paper",
                "needs_wizard": needs_wizard(),
            },
        )

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return page(request)

    @app.get("/setup", response_class=HTMLResponse)
    async def setup(request: Request) -> HTMLResponse:
        return page(request)

    @app.get("/api/health")
    async def health() -> dict:
        return {
            "ok": True,
            "killed": engine.risk.killed,
            "kill_source": engine.risk.kill_source,
            "version": VERSION,
            "product": PRODUCT,
        }

    @app.get("/api/snapshot")
    async def snapshot() -> dict:
        return engine.snapshot()

    @app.get("/api/recovery-commit")
    async def recovery_commit() -> dict:
        snap = engine.snapshot()
        return {
            "handoff_atomic_ready": snap["stats"]["handoff_atomic_ready"],
            "recovery_commit_pass": snap["stats"]["recovery_commit_pass"],
            "recovery_research_pass": snap["stats"]["recovery_research_pass"],
            "recovery_cancel": engine.stats.recovery_cancel,
            "paper_opened": snap["stats"]["paper_opened"],
            "records": snap["recovery_commit"],
            "pipeline": "ATOMIC_READY → Final Commit → COMMIT|RESEARCH_COMMIT|CANCEL → Paper Lab → CAPTURED|REVERSED|MISSED|EXPIRED",
        }

    @app.get("/api/journal")
    async def journal() -> dict:
        return {"entries": [e.to_dict() for e in engine.journal.entries], "chain_ok": engine.journal.verify_chain()}

    @app.get("/api/academy")
    async def academy() -> dict:
        return {"lessons": LESSONS}

    @app.get("/api/wizard")
    async def wizard_state() -> dict:
        return {"needed": needs_wizard(), "steps": STEPS}

    @app.post("/api/wizard/complete")
    async def wizard_done() -> dict:
        mark_complete()
        return {"needed": False}

    @app.get("/api/updates")
    async def updates() -> dict:
        return check_for_updates()

    @app.post("/api/kill")
    async def kill() -> dict:
        engine.risk.kill(KillSource.CUSTOMER)
        await engine.broadcast()
        return {"killed": True, "source": engine.risk.kill_source}

    @app.post("/api/resume")
    async def resume() -> dict:
        ok = engine.risk.resume(KillSource.CUSTOMER)
        await engine.broadcast()
        return {"killed": engine.risk.killed, "resumed": ok}

    @app.post("/api/mode")
    async def set_mode(body: ModeBody) -> dict:
        mode = OperatingMode(body.mode.lower())
        engine.set_mode(mode)
        await engine.broadcast()
        return {"mode": engine.pipeline.mode.value}

    @app.post("/api/approve")
    async def approve(body: ApproveBody) -> dict:
        return await engine.approve(body.opportunity_id)

    @app.post("/api/reauth")
    async def reauth(body: ReauthBody) -> dict:
        engine.takeover.reauthenticate(body.device_id, body.ip, body.geo)
        if engine.risk.kill_source == KillSource.SECURITY.value:
            engine.risk.resume(KillSource.CUSTOMER)
        await engine.broadcast()
        return {"suspended": engine.takeover.suspended}

    @app.get("/api/rejection/{opportunity_id}")
    async def rejection(opportunity_id: str) -> dict:
        for opp in engine.opportunities:
            if opp.id == opportunity_id:
                return explain_rejection(opp.why_blocked)
        return explain_rejection(["Unknown opportunity"])

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
