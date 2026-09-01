from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import create_engine, inspect as sa_inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from fgislk.settings import DATA_KIND, DATA_KIND_LABELS, database_url, max_workers
from fgislk.windows import AUDIT_START

_UPSERT = text(
    """
    INSERT INTO taxation_piece (
        subject, fgis_id, taxation_piece, quarter, area, status, read_at,
        actuality_date
    )
    VALUES (
        :subject, :fgis_id, :taxation_piece, :quarter, :area, :status, :read_at,
        :actuality_date
    )
    ON CONFLICT (subject, fgis_id) DO UPDATE SET
        taxation_piece = EXCLUDED.taxation_piece,
        quarter = EXCLUDED.quarter,
        area = EXCLUDED.area,
        status = EXCLUDED.status,
        read_at = EXCLUDED.read_at,
        actuality_date = COALESCE(EXCLUDED.actuality_date, taxation_piece.actuality_date)
    """
)

_INSERT_HISTORY = text(
    """
    INSERT INTO fgis_import_history (
        subject, day, result, updated_count, data_kind, error, ran_at,
        period_start, period_end
    )
    VALUES (
        :subject, :day, :result, :updated_count, :data_kind, :error, :ran_at,
        :period_start, :period_end
    )
    """
)

_RECENT_IDS = text(
    """
    SELECT fgis_id FROM taxation_piece
    WHERE subject = :subject AND read_at >= :since
    """
)


def make_engine() -> Engine:
    workers = max_workers()
    return create_engine(
        database_url(),
        pool_pre_ping=True,
        pool_size=workers + 2,
        max_overflow=4,
    )


def db_revision(eng: Engine) -> str | None:
    try:
        with eng.connect() as conn:
            if not sa_inspect(conn).has_table("alembic_version"):
                return None
            row = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            return str(row) if row else None
    except SQLAlchemyError:
        return None


def last_ok_day(conn: Connection, subject: str) -> date | None:
    """Закрытый день инкремента: только ok с окном СПД не-аудита.

    Аудит (period_start = 2023-05-01) даёт day конца окна — для догона это ещё
    не закрытый календарный день (watermark = day − 1). Строка без окна
    (старый ok, skip) день не закрывает. Последняя error — повторить её day.
    """
    watermark = conn.execute(
        text(
            """
            SELECT MAX(
                CASE
                    WHEN period_start IS NULL THEN NULL
                    WHEN period_start = CAST(:audit_start AS date) THEN (day - 1)
                    ELSE day
                END
            )
            FROM fgis_import_history
            WHERE subject = :subject AND data_kind = :kind AND result = 'ok'
            """
        ),
        {
            "subject": subject,
            "kind": DATA_KIND,
            "audit_start": AUDIT_START,
        },
    ).scalar()
    latest = conn.execute(
        text(
            """
            SELECT day, result
            FROM fgis_import_history
            WHERE subject = :subject AND data_kind = :kind
            ORDER BY ran_at DESC, id DESC
            LIMIT 1
            """
        ),
        {"subject": subject, "kind": DATA_KIND},
    ).mappings().first()
    if latest is not None and latest["result"] == "error":
        failed = latest["day"]
        if failed is not None and (watermark is None or watermark >= failed):
            return failed - timedelta(days=1)
    return watermark


def try_lock_subject(conn: Connection, subject: str) -> bool:
    locked = conn.execute(
        text("SELECT pg_try_advisory_lock(hashtext(:key))"),
        {"key": f"fgislk:{DATA_KIND}:{subject}"},
    ).scalar()
    conn.commit()
    return bool(locked)


def unlock_subject(conn: Connection, subject: str) -> None:
    conn.execute(
        text("SELECT pg_advisory_unlock(hashtext(:key))"),
        {"key": f"fgislk:{DATA_KIND}:{subject}"},
    )
    conn.commit()


def upsert_piece(conn: Connection, row: dict[str, Any]) -> None:
    conn.execute(_UPSERT, row)


def recent_read_ids(conn: Connection, subject: str, since: date) -> set[str]:
    rows = conn.execute(_RECENT_IDS, {"subject": subject, "since": since})
    return {str(row[0]) for row in rows}


def write_history(
    conn: Connection,
    *,
    subject: str,
    day: date,
    result: str,
    updated_count: int,
    error: str | None,
    period_start: date | None = None,
    period_end: date | None = None,
) -> None:
    conn.execute(
        _INSERT_HISTORY,
        {
            "subject": subject,
            "day": day,
            "result": result,
            "updated_count": updated_count,
            "data_kind": DATA_KIND,
            "error": error,
            "ran_at": datetime.now(timezone.utc),
            "period_start": period_start,
            "period_end": period_end,
        },
    )
    conn.commit()


def kind_label(kind: str | None) -> str:
    if not kind:
        return DATA_KIND_LABELS[DATA_KIND]
    return DATA_KIND_LABELS.get(kind, kind)


def progress_label(updated: int, total: int | None) -> str | None:
    if total is None:
        return None
    if total <= 0:
        return "100%"
    return f"{min(100, int(updated * 100 / total))}%"


def is_audit(
    *,
    period_start: date | str | None,
    mode: str | None = None,
) -> bool:
    if mode == "audit":
        return True
    if mode == "incremental":
        return False
    if period_start is None:
        return False
    start = (
        date.fromisoformat(period_start)
        if isinstance(period_start, str)
        else period_start
    )
    return start == AUDIT_START


def _public_row(
    row: Any,
    *,
    in_progress: bool = False,
    mode: str | None = None,
) -> dict[str, Any]:
    data = dict(row)
    period_start = data.get("period_start")
    period_end = data.get("period_end")
    day = data.get("day")
    kind = data.get("data_kind") or DATA_KIND
    ran = data.get("ran_at")
    return {
        "subject": data["subject"],
        "day": day if isinstance(day, str) or day is None else day.isoformat(),
        "result": data["result"],
        "updated_count": data["updated_count"],
        "error": data.get("error"),
        "ran_at": ran.isoformat() if hasattr(ran, "isoformat") else ran,
        "period_start": (
            period_start
            if isinstance(period_start, str) or period_start is None
            else period_start.isoformat()
        ),
        "period_end": (
            period_end
            if isinstance(period_end, str) or period_end is None
            else period_end.isoformat()
        ),
        "data_kind": kind,
        "data_kind_label": kind_label(kind),
        "audit": is_audit(period_start=period_start, mode=mode),
        "in_progress": in_progress,
        "progress": None,
    }


def _live_row(job: dict[str, Any], last: dict[str, Any] | None) -> dict[str, Any]:
    kind = job.get("data_kind") or DATA_KIND
    updated = job.get("updated_count", 0)
    item: dict[str, Any] = {
        "subject": job["subject"],
        "day": None,
        "result": "running",
        "updated_count": updated,
        "error": None,
        "ran_at": None,
        "period_start": job.get("period_start"),
        "period_end": job.get("period_end"),
        "data_kind": kind,
        "data_kind_label": kind_label(kind),
        "audit": is_audit(
            period_start=job.get("period_start"), mode=job.get("mode")
        ),
        "in_progress": True,
        "mode": job.get("mode"),
        "progress": progress_label(updated, job.get("changed_total")),
    }
    if job.get("changed_total") is not None:
        item["changed_total"] = job["changed_total"]
    if last is not None:
        item["last"] = last
    return item


def overlay_status(
    subjects: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
    *,
    view_day: date,
    today: date,
) -> list[dict[str, Any]]:
    last_by_subject: dict[str, dict[str, Any]] = {}
    for row in subjects:
        last_by_subject.setdefault(row["subject"], row)
    live_codes: set[str] = set()
    out: list[dict[str, Any]] = []
    for job in jobs:
        end_raw = job.get("period_end")
        if end_raw:
            end_d = (
                date.fromisoformat(end_raw) if isinstance(end_raw, str) else end_raw
            )
            if end_d != view_day:
                continue
        elif view_day != today:
            continue
        live_codes.add(job["subject"])
        out.append(_live_row(job, last_by_subject.get(job["subject"])))
    for row in subjects:
        if row["subject"] in live_codes:
            continue
        item = dict(row)
        item["in_progress"] = False
        out.append(item)
    out.sort(key=lambda row: (not row.get("in_progress"), row["subject"]))
    return out


def status_day_meta(view_day: date, today: date) -> dict[str, str | None]:
    prev = view_day - timedelta(days=1)
    nxt = view_day + timedelta(days=1)
    return {
        "day": view_day.isoformat(),
        "prev_day": prev.isoformat() if prev >= AUDIT_START else None,
        "next_day": nxt.isoformat() if nxt <= today else None,
    }


def status_rows(
    eng: Engine,
    *,
    day: date,
    subject: str | None = None,
    data_kind: str | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"day": day}
    where = ["period_end = :day"]
    if data_kind:
        where.append("data_kind = :kind")
        params["kind"] = data_kind
    if subject:
        where.append("subject = :subject")
        params["subject"] = subject
    sql = text(
        f"""
        SELECT DISTINCT ON (subject)
            subject, day, result, updated_count, error, ran_at,
            period_start, period_end, data_kind
        FROM fgis_import_history
        WHERE {' AND '.join(where)}
        ORDER BY subject, updated_count DESC, ran_at DESC, id DESC
        """
    )
    with eng.connect() as conn:
        rows = conn.execute(sql, params).mappings().all()
    return [_public_row(row) for row in rows]


def history_rows(
    eng: Engine, *, subject: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    cap = max(1, min(limit, 500))
    params: dict[str, Any] = {"kind": DATA_KIND, "lim": cap}
    where = "data_kind = :kind"
    if subject:
        where += " AND subject = :subject"
        params["subject"] = subject
    sql = text(
        f"""
        SELECT subject, day, result, updated_count, error, ran_at,
               period_start, period_end, data_kind
        FROM fgis_import_history
        WHERE {where}
        ORDER BY ran_at DESC, id DESC
        LIMIT :lim
        """
    )
    with eng.connect() as conn:
        rows = conn.execute(sql, params).mappings().all()
    return [_public_row(row) for row in rows]
