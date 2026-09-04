from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from api import __version__
from api.gate import migrate_ready, wait_schema
from api.panel import panel_manifest
from api.quarters import router as quarters_router
from api.settings import REQUIRED_SCHEMA
from api.store import db_revision, make_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = make_engine()
    await wait_schema(engine)
    app.state.engine = engine
    yield
    engine.dispose()


app = FastAPI(title="api", version=__version__, lifespan=lifespan)
app.include_router(quarters_router)


@app.get("/health")
def health() -> dict:
    engine = app.state.engine
    return {
        "status": "ok",
        "version": __version__,
        "alembic_revision": db_revision(engine),
    }


@app.get("/ready")
async def ready():
    engine = app.state.engine
    revision = db_revision(engine)
    migrate_ok = await migrate_ready()
    ok = migrate_ok and revision == REQUIRED_SCHEMA
    body = {
        "ok": ok,
        "revision": revision,
        "required": REQUIRED_SCHEMA,
        "migrate": migrate_ok,
    }
    if ok:
        return body
    return JSONResponse(status_code=503, content=body)


@app.get("/panel")
def panel() -> dict:
    return panel_manifest()


@app.get("/status")
def status() -> dict:
    engine = app.state.engine
    revision = db_revision(engine)
    return {
        "process": "alive",
        "version": __version__,
        "revision": revision,
        "alembic_revision": revision,
        "required_schema": REQUIRED_SCHEMA,
    }
