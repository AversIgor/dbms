from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import create_engine, inspect as sa_inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from fgislk.settings import DATA_KIND, database_url, max_workers

_UPSERT = text(
    """
    INSERT INTO taxation_piece (
        subject, fgis_id, taxation_piece, quarter, area, status, read_at
    )
    VALUES (
        :subject, :fgis_id, :taxation_piece, :quarter, :area, :status, :read_at
    )
    ON CONFLICT (subject, fgis_id) DO UPDATE SET
        taxation_piece = EXCLUDED.taxation_piece,
        quarter = EXCLUDED.quarter,
        area = EXCLUDED.area,
        status = EXCLUDED.status,
        read_at = EXCLUDED.read_at
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
    value = conn.execute(
        text(
            "SELECT MAX(day) FROM fgis_import_history "
            "WHERE subject = :subject AND data_kind = :kind AND result = 'ok'"
        ),
        {"subject": subject, "kind": DATA_KIND},
    ).scalar()
    return value


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


def overlay_status(
    subjects: list[dict[str, Any]], jobs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_subject = {job["subject"]: job for job in jobs}
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in subjects:
        code = row["subject"]
        seen.add(code)
        item = dict(row)
        job = by_subject.get(code)
        if job is None:
            item["in_progress"] = False
        else:
            item["in_progress"] = True
            item["result"] = "running"
            item["error"] = None
            item["mode"] = job.get("mode")
            if job.get("period_start") is not None:
                item["period_start"] = job["period_start"]
            if job.get("period_end") is not None:
                item["period_end"] = job["period_end"]
            if "updated_count" in job:
                item["updated_count"] = job["updated_count"]
            if job.get("changed_total") is not None:
                item["changed_total"] = job["changed_total"]
        out.append(item)
    for job in jobs:
        if job["subject"] in seen:
            continue
        out.append(
            {
                "subject": job["subject"],
                "day": None,
                "result": "running",
                "updated_count": job.get("updated_count", 0),
                "error": None,
                "ran_at": None,
                "period_start": job.get("period_start"),
                "period_end": job.get("period_end"),
                "in_progress": True,
                "mode": job.get("mode"),
            }
        )
        if job.get("changed_total") is not None:
            out[-1]["changed_total"] = job["changed_total"]
    out.sort(key=lambda row: row["subject"])
    return out


def status_rows(eng: Engine) -> list[dict[str, Any]]:
    sql = text(
        """
        SELECT DISTINCT ON (subject)
            subject, day, result, updated_count, error, ran_at,
            period_start, period_end
        FROM fgis_import_history
        WHERE data_kind = :kind
        ORDER BY subject, ran_at DESC, id DESC
        """
    )
    with eng.connect() as conn:
        rows = conn.execute(sql, {"kind": DATA_KIND}).mappings().all()
    return [
        {
            "subject": row["subject"],
            "day": row["day"].isoformat() if row["day"] else None,
            "result": row["result"],
            "updated_count": row["updated_count"],
            "error": row["error"],
            "ran_at": row["ran_at"].isoformat() if row["ran_at"] else None,
            "period_start": (
                row["period_start"].isoformat() if row["period_start"] else None
            ),
            "period_end": row["period_end"].isoformat() if row["period_end"] else None,
        }
        for row in rows
    ]
