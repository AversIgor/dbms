from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from constants import __version__
from constants.gate import migrate_ready, wait_schema
from constants.panel import panel_manifest
from constants.settings import REQUIRED_SCHEMA
from constants.store import (
    ConstantTypeError,
    db_revision,
    get_item,
    list_items,
    make_engine,
    put_item,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = make_engine()
    await wait_schema(engine)
    app.state.engine = engine
    yield
    engine.dispose()


app = FastAPI(title="constants", version=__version__, lifespan=lifespan)


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
        "count": len(list_items(engine)),
    }


@app.get("/items")
def items() -> dict:
    return {"rows": list_items(app.state.engine)}


@app.get("/items/{key}")
def item(key: str):
    found = get_item(app.state.engine, key)
    if found is None:
        return JSONResponse(
            status_code=404, content={"ok": False, "error": f"нет ключа {key}"}
        )
    return found


@app.put("/items/{key}")
async def save_item(key: str, request: Request):
    try:
        payload = await request.json()
    except ValueError:
        return JSONResponse(
            status_code=400, content={"ok": False, "error": "нужен JSON"}
        )
    if not isinstance(payload, dict) or "value" not in payload:
        return JSONResponse(
            status_code=400, content={"ok": False, "error": "тело — {value}"}
        )
    try:
        return put_item(app.state.engine, key, payload["value"])
    except KeyError:
        return JSONResponse(
            status_code=404, content={"ok": False, "error": f"нет ключа {key}"}
        )
    except ConstantTypeError as exc:
        return JSONResponse(status_code=400, content={"ok": False, "error": str(exc)})
