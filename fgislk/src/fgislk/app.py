from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from fgislk import __version__
from fgislk.gate import migrate_ready, wait_schema
from fgislk.settings import REQUIRED_SCHEMA
from fgislk.spd import SpdClient
from fgislk.store import db_revision, make_engine, overlay_status, status_rows
from fgislk.sync import (
    JobSet,
    RunningSet,
    daily_loop,
    run_subjects,
)
from fgislk.windows import normalize_subject, parse_audit_day

_jobs: JobSet = JobSet()


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = make_engine()
    running = RunningSet()
    jobs = JobSet()
    await wait_schema(engine)
    stop = asyncio.Event()
    daily = asyncio.create_task(daily_loop(engine, running, stop, jobs))
    app.state.engine = engine
    app.state.running = running
    app.state.jobs = jobs
    app.state.stop = stop
    app.state.daily = daily
    yield
    stop.set()
    jobs.cancel_all()
    daily.cancel()
    engine.dispose()


app = FastAPI(title="fgislk", version=__version__, lifespan=lifespan)


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _jobs_of() -> JobSet:
    jobs = getattr(app.state, "jobs", None)
    return jobs if jobs is not None else _jobs


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


@app.get("/status")
async def status() -> dict:
    engine = app.state.engine
    running: RunningSet = app.state.running
    revision = db_revision(engine)
    jobs = await running.snapshot()
    subjects = overlay_status(status_rows(engine), jobs)
    return {
        "process": "alive",
        "version": __version__,
        "alembic_revision": revision,
        "required_schema": REQUIRED_SCHEMA,
        "running": [job["subject"] for job in jobs],
        "updated_count_total": sum(row["updated_count"] for row in subjects),
        "subjects": subjects,
    }


@app.get("/sync")
async def sync(
    start: str | None = Query(default=None),
    audit: str | None = Query(default=None),
    stop: str | None = Query(default=None),
    subject: str | None = Query(default=None),
    day: str | None = Query(default=None),
):
    want_start = _truthy(start)
    want_audit = _truthy(audit)
    want_stop = _truthy(stop)
    flags = sum((want_start, want_audit, want_stop))
    if flags == 0:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "нужен start=1, audit=1 или stop=1"},
        )
    if flags > 1:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "start, audit и stop вместе нельзя"},
        )
    has_day = day is not None and day.strip() != ""
    if has_day and not want_audit:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "day= только с audit=1"},
        )
    if want_stop:
        if subject is not None and subject.strip() != "":
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "stop без subject="},
            )
        cancelled = _jobs_of().cancel_all()
        return {"ok": True, "stopped": True, "cancelled": cancelled}

    audit_from = None
    if has_day:
        try:
            audit_from = parse_audit_day(day)
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"ok": False, "error": str(exc)})

    codes: list[str] | None
    if subject is None or subject.strip() == "":
        codes = None
        require_lock = False
    else:
        try:
            codes = [normalize_subject(subject)]
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"ok": False, "error": str(exc)})
        require_lock = True

    running: RunningSet = app.state.running
    live = await running.codes()
    if require_lock and codes is not None and codes[0] in live:
        return JSONResponse(
            status_code=409,
            content={"ok": False, "error": f"импорт субъекта {codes[0]} уже идёт"},
        )
    if not require_lock and live:
        return JSONResponse(
            status_code=409,
            content={"ok": False, "error": "импорт уже идёт; GET /sync?stop=1"},
        )

    engine = app.state.engine

    async def job() -> None:
        spd = SpdClient()
        try:
            await run_subjects(
                engine=engine,
                spd=spd,
                running=running,
                subjects=codes,
                audit=want_audit,
                require_lock=require_lock,
                audit_from=audit_from,
            )
        finally:
            await spd.aclose()

    _jobs_of().track(asyncio.create_task(job()))
    return JSONResponse(
        status_code=202,
        content={
            "ok": True,
            "audit": want_audit,
            "day": audit_from.isoformat() if audit_from is not None else None,
            "subjects": codes if codes is not None else "01-99",
        },
    )
