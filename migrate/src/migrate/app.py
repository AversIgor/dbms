from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from migrate import __version__
from migrate.panel import panel_manifest
from migrate.schema import inspect_schema, revision_history
from migrate.state import last_upgrade

app = FastAPI(title="migrate", version=__version__)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
def ready():
    info = inspect_schema()
    if info["database"] and info["in_sync"] and info["revision"]:
        return {"ok": True, "revision": info["revision"]}
    return JSONResponse(
        status_code=503,
        content={
            "ok": False,
            "revision": info["revision"],
            "head": info["head"],
            "error": info["error"],
        },
    )


@app.get("/status")
def status() -> dict:
    info = inspect_schema()
    upgrade = last_upgrade()
    return {
        "process": "alive",
        "database": info["database"],
        "revision": info["revision"],
        "head": info["head"],
        "in_sync": info["in_sync"],
        "postgis": info["postgis"],
        "error": info["error"],
        "last_upgrade": {
            "ok": upgrade.ok,
            "message": upgrade.message,
            "at": upgrade.at,
            "revision": upgrade.revision,
        },
        "history": revision_history(),
    }


@app.get("/panel")
def panel() -> dict:
    return panel_manifest()


@app.get("/settings")
def settings() -> dict:
    return {"writable": False, "values": {}}
