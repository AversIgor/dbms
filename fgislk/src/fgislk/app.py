from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from fgislk import __version__
from fgislk.gate import migrate_ready, wait_schema
from fgislk.panel import panel_manifest
from fgislk.settings import (
    DATA_KIND,
    IMPORT_ORDER,
    KIND_CLEARCUT,
    REQUIRED_SCHEMA,
    apply_settings,
    settings_view,
)
from fgislk.spd import SpdClient
from fgislk.store import (
    db_revision,
    history_rows,
    make_engine,
    overlay_status,
    quarter_exists,
    status_day_meta,
    status_rows,
)
from fgislk.sync import (
    RunningSet,
    daily_loop,
    run_subjects,
    stop_import,
)
from fgislk.windows import (
    AUDIT_START,
    moscow_today,
    parse_audit_day,
    parse_subjects,
    subject_from_quarter_id,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = make_engine()
    running = RunningSet()
    await wait_schema(engine)
    stop = asyncio.Event()
    kick = asyncio.Event()
    daily = asyncio.create_task(daily_loop(engine, running, stop, kick))
    app.state.engine = engine
    app.state.running = running
    app.state.stop = stop
    app.state.kick = kick
    app.state.daily = daily
    yield
    stop.set()
    running.cancel_tasks()
    daily.cancel()
    engine.dispose()


app = FastAPI(title="fgislk", version=__version__, lifespan=lifespan)


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _audit_kinds(
    quarters: str | None,
    taxation_piece: str | None,
    clearcut: str | None,
) -> list[str] | None:
    flags = {
        "quarters": quarters,
        "taxation_piece": taxation_piece,
        "clearcut": clearcut,
    }
    if not any(raw is not None and raw.strip() != "" for raw in flags.values()):
        return None
    return [kind for kind in IMPORT_ORDER if _truthy(flags.get(kind))]


def _running_of() -> RunningSet:
    running = getattr(app.state, "running", None)
    if running is None:
        raise RuntimeError("fgislk не запущен")
    return running


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


@app.get("/history")
def history(
    subject: str | None = Query(default=None),
    data_kind: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    code = None
    if subject is not None and subject.strip() != "":
        try:
            codes = parse_subjects(subject)
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"ok": False, "error": str(exc)})
        if len(codes) != 1:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "history — один subject="},
            )
        code = codes[0]
    kind = (data_kind or "").strip() or None
    engine = app.state.engine
    return {"rows": history_rows(engine, subject=code, data_kind=kind, limit=limit)}


@app.get("/settings")
def get_settings() -> dict:
    return settings_view()


@app.put("/settings")
async def put_settings(request: Request):
    try:
        payload = await request.json()
    except ValueError:
        return JSONResponse(
            status_code=400, content={"ok": False, "error": "нужен JSON"}
        )
    try:
        return apply_settings(payload)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"ok": False, "error": str(exc)})


@app.get("/status")
async def status(
    subject: str | None = Query(default=None),
    data_kind: str | None = Query(default=None),
    day: str | None = Query(default=None),
):
    engine = app.state.engine
    running: RunningSet = app.state.running
    today = moscow_today()
    if day is None or day.strip() == "":
        view_day = today
    else:
        try:
            view_day = date.fromisoformat(day.strip())
        except ValueError:
            return JSONResponse(
                status_code=400, content={"ok": False, "error": "day=YYYY-MM-DD"}
            )
        if view_day > today:
            view_day = today
        if view_day < AUDIT_START:
            view_day = AUDIT_START
    codes_filter: list[str] | None = None
    if subject is not None and subject.strip() != "":
        try:
            codes_filter = parse_subjects(subject)
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"ok": False, "error": str(exc)})
    kind = (data_kind or "").strip() or None
    revision = db_revision(engine)
    jobs = await running.snapshot()
    if codes_filter is not None:
        wanted = set(codes_filter)
        jobs = [job for job in jobs if job["subject"] in wanted]
    if kind is not None:
        jobs = [
            job
            for job in jobs
            if (job.get("data_kind") or DATA_KIND) == kind
        ]
    status_subject = (
        codes_filter[0] if codes_filter is not None and len(codes_filter) == 1 else None
    )
    subjects = overlay_status(
        status_rows(engine, day=view_day, subject=status_subject, data_kind=kind),
        jobs,
        view_day=view_day,
        today=today,
    )
    if codes_filter is not None and len(codes_filter) > 1:
        wanted = set(codes_filter)
        subjects = [row for row in subjects if row["subject"] in wanted]
    live = [row for row in subjects if row["in_progress"]]
    body = {
        "process": "alive",
        "version": __version__,
        "alembic_revision": revision,
        "required_schema": REQUIRED_SCHEMA,
        "running": [job["subject"] for job in jobs],
        "updated_count_total": sum(row["updated_count"] for row in live),
        "subjects": subjects,
    }
    body.update(status_day_meta(view_day, today))
    return body


@app.get("/sync")
async def sync(
    start: str | None = Query(default=None),
    audit: str | None = Query(default=None),
    stop: str | None = Query(default=None),
    subject: str | None = Query(default=None),
    day: str | None = Query(default=None),
    quarters: str | None = Query(default=None),
    taxation_piece: str | None = Query(default=None),
    clearcut: str | None = Query(default=None),
    quarter: str | None = Query(default=None),
    area: str | None = Query(default=None),
):
    want_start = _truthy(start)
    want_audit = _truthy(audit)
    want_stop = _truthy(stop)
    quarter_id = (quarter or "").strip() or None
    want_point = _truthy(clearcut) and quarter_id is not None
    if _truthy(clearcut) and quarter_id is None and not want_audit:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "clearcut=1 с quarter= или с audit=1"},
        )
    if quarter_id is not None and not want_point:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "quarter= только с clearcut=1 без start/audit/stop"},
        )
    flags = sum((want_start, want_audit, want_stop, want_point))
    if flags == 0:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "нужен start=1, audit=1, stop=1 или clearcut=1&quarter=",
            },
        )
    if flags > 1:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "start, audit, stop и точечный опрос вместе нельзя"},
        )
    has_day = day is not None and day.strip() != ""
    if has_day and not want_audit:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "day= только с audit=1"},
        )
    has_kind_flag = any(
        raw is not None and raw.strip() != ""
        for raw in (quarters, taxation_piece)
    )
    if want_audit and clearcut is not None and str(clearcut).strip() != "":
        has_kind_flag = True
    if has_kind_flag and not want_audit:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "quarters=, taxation_piece= и clearcut= только с audit=1",
            },
        )
    has_area_flag = area is not None and area.strip() != ""
    if has_area_flag and not want_audit and not want_start:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "area= только с audit=1"},
        )
    if want_stop:
        if subject is not None and subject.strip() != "":
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "stop без subject="},
            )
        cancelled = await stop_import(_running_of())
        return {"ok": True, "stopped": True, "cancelled": cancelled}

    audit_from = None
    if has_day:
        try:
            audit_from = parse_audit_day(day)
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"ok": False, "error": str(exc)})

    kinds: list[str] | None = None
    if want_audit:
        kinds = _audit_kinds(quarters, taxation_piece, clearcut)
        if kinds is not None and not kinds:
            return JSONResponse(
                status_code=400,
                content={
                    "ok": False,
                    "error": "аудит: отметьте выделы, кварталы и/или лесосеки",
                },
            )
    if want_point:
        kinds = [KIND_CLEARCUT]

    need_area = True if want_start or want_point else _truthy(area)

    codes: list[str] | None
    require_lock: bool
    if want_point:
        assert quarter_id is not None
        try:
            derived = subject_from_quarter_id(quarter_id)
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"ok": False, "error": str(exc)})
        if subject is not None and subject.strip() != "":
            try:
                given = parse_subjects(subject)
            except ValueError as exc:
                return JSONResponse(
                    status_code=400, content={"ok": False, "error": str(exc)}
                )
            if len(given) != 1 or given[0] != derived:
                return JSONResponse(
                    status_code=400,
                    content={"ok": False, "error": "subject= не совпадает с номером квартала"},
                )
        codes = [derived]
        require_lock = True
        if not quarter_exists(app.state.engine, derived, quarter_id):
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "квартал не найден в quarters"},
            )
    elif subject is None or subject.strip() == "":
        codes = None
        require_lock = False
    else:
        try:
            codes = parse_subjects(subject)
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"ok": False, "error": str(exc)})
        require_lock = True

    running: RunningSet = app.state.running
    live = await running.codes()
    if require_lock and codes is not None:
        overlap = [code for code in codes if code in live]
        if overlap:
            shown = ",".join(overlap)
            return JSONResponse(
                status_code=409,
                content={"ok": False, "error": f"импорт субъекта {shown} уже идёт"},
            )
    if not require_lock and await running.inflight():
        return JSONResponse(
            status_code=409,
            content={"ok": False, "error": "импорт уже идёт; GET /sync?stop=1"},
        )
    if not await running.inflight():
        running.reset()

    started = {
        "ok": True,
        "audit": want_audit,
        "day": audit_from.isoformat() if audit_from is not None else None,
        "subjects": codes if codes is not None else "01-99",
        "kinds": kinds if kinds is not None else list(IMPORT_ORDER),
        "area": need_area,
        "quarter": quarter_id,
    }
    if want_start and codes is None:
        kick: asyncio.Event = app.state.kick
        kick.set()
        return JSONResponse(status_code=202, content=started)

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
                kinds=kinds,
                need_area=need_area,
                quarter_id=quarter_id if want_point else None,
            )
        finally:
            await spd.aclose()

    running.track(asyncio.create_task(job()))
    return JSONResponse(status_code=202, content=started)
