from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import bindparam, create_engine, inspect as sa_inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from fgislk.settings import DATA_KIND, DATA_KIND_LABELS, KIND_TABLE, database_url, http_workers
from fgislk.windows import AUDIT_START

_UPSERT = text(
    """
    INSERT INTO taxation_piece (
        subject, fgis_id, taxation_piece, quarter, area, status, read_at,
        actuality_date, geom, crs
    )
    VALUES (
        :subject, :fgis_id, :taxation_piece, :quarter, :area, :status, :read_at,
        :actuality_date, ST_GeomFromText(:geom), :crs
    )
    ON CONFLICT (fgis_id) DO UPDATE SET
        subject = EXCLUDED.subject,
        taxation_piece = EXCLUDED.taxation_piece,
        quarter = EXCLUDED.quarter,
        area = EXCLUDED.area,
        status = EXCLUDED.status,
        read_at = EXCLUDED.read_at,
        actuality_date = COALESCE(EXCLUDED.actuality_date, taxation_piece.actuality_date),
        geom = COALESCE(EXCLUDED.geom, taxation_piece.geom),
        crs = COALESCE(EXCLUDED.crs, taxation_piece.crs)
    """
)

_UPSERT_QUARTERS = text(
    """
    INSERT INTO quarters (
        subject, fgis_id, subforestry, quarter, tract, status, read_at,
        actuality_date, geom, crs
    )
    VALUES (
        :subject, :fgis_id, :subforestry, :quarter, :tract, :status, :read_at,
        :actuality_date, ST_GeomFromText(:geom), :crs
    )
    ON CONFLICT (fgis_id) DO UPDATE SET
        subject = EXCLUDED.subject,
        subforestry = EXCLUDED.subforestry,
        quarter = EXCLUDED.quarter,
        tract = COALESCE(EXCLUDED.tract, quarters.tract),
        status = EXCLUDED.status,
        read_at = EXCLUDED.read_at,
        actuality_date = COALESCE(EXCLUDED.actuality_date, quarters.actuality_date),
        geom = COALESCE(EXCLUDED.geom, quarters.geom),
        crs = COALESCE(EXCLUDED.crs, quarters.crs)
    """
)

_UPSERT_CLEARCUT = text(
    """
    INSERT INTO clearcut (
        subject, fgis_id, quarter, area, status, read_at,
        actuality_date, geom, crs, limitation_dt, clearcut_no, basis_doc_no
    )
    VALUES (
        :subject, :fgis_id, :quarter, :area, :status, :read_at,
        :actuality_date, ST_GeomFromText(:geom), :crs, :limitation_dt,
        :clearcut_no, :basis_doc_no
    )
    ON CONFLICT (fgis_id) DO UPDATE SET
        subject = EXCLUDED.subject,
        quarter = EXCLUDED.quarter,
        area = EXCLUDED.area,
        status = EXCLUDED.status,
        read_at = EXCLUDED.read_at,
        actuality_date = COALESCE(EXCLUDED.actuality_date, clearcut.actuality_date),
        geom = COALESCE(EXCLUDED.geom, clearcut.geom),
        crs = COALESCE(EXCLUDED.crs, clearcut.crs),
        limitation_dt = COALESCE(EXCLUDED.limitation_dt, clearcut.limitation_dt),
        clearcut_no = EXCLUDED.clearcut_no,
        basis_doc_no = COALESCE(EXCLUDED.basis_doc_no, clearcut.basis_doc_no)
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

_RECENT_ID_CHUNK = 1000


def make_engine() -> Engine:
    workers = http_workers()
    return create_engine(
        database_url(),
        pool_pre_ping=True,
        pool_size=workers + 2,
        max_overflow=4,
        connect_args={
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 3,
        },
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


def last_ok_day(conn: Connection, subject: str, data_kind: str) -> date | None:
    """Закрытый день: ok с окном СПД (инкремент и аудит, day = вчера прогона).

    Старые строки аудита писали в day конец окна (сегодня прогона) — для них
    watermark = day − 1, иначе следующий инкремент пропускает вчера.
    Без окна день не закрывает. Последняя error — повторить её day.
    """
    watermark = conn.execute(
        text(
            """
            SELECT MAX(
                CASE
                    WHEN period_start IS NULL THEN NULL
                    WHEN period_start = CAST(:audit_start AS date)
                         AND day = period_end THEN (day - 1)
                    ELSE day
                END
            )
            FROM fgis_import_history
            WHERE subject = :subject AND data_kind = :kind AND result = 'ok'
            """
        ),
        {
            "subject": subject,
            "kind": data_kind,
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
        {"subject": subject, "kind": data_kind},
    ).mappings().first()
    if latest is not None and latest["result"] == "error":
        failed = latest["day"]
        if failed is not None and (watermark is None or watermark >= failed):
            return failed - timedelta(days=1)
    return watermark


def try_lock_subject(conn: Connection, subject: str) -> bool:
    locked = conn.execute(
        text("SELECT pg_try_advisory_lock(hashtext(:key))"),
        {"key": f"fgislk:{subject}"},
    ).scalar()
    conn.commit()
    return bool(locked)


def unlock_subject(conn: Connection, subject: str) -> None:
    conn.execute(
        text("SELECT pg_advisory_unlock(hashtext(:key))"),
        {"key": f"fgislk:{subject}"},
    )
    conn.commit()


def ping_lock(conn: Connection) -> None:
    conn.execute(text("SELECT 1"))
    conn.commit()


def upsert_pieces(conn: Connection, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        return
    conn.execute(
        _UPSERT,
        [
            {
                "subject": row.get("subject"),
                "fgis_id": row.get("fgis_id"),
                "taxation_piece": row.get("taxation_piece"),
                "quarter": row.get("quarter"),
                "area": row.get("area"),
                "status": row.get("status"),
                "read_at": row.get("read_at"),
                "actuality_date": row.get("actuality_date"),
                "geom": row.get("geom"),
                "crs": row.get("crs"),
            }
            for row in rows
        ],
    )


def upsert_quarters(conn: Connection, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        return
    conn.execute(
        _UPSERT_QUARTERS,
        [
            {
                "subject": row.get("subject"),
                "fgis_id": row.get("fgis_id"),
                "subforestry": row.get("subforestry"),
                "quarter": row.get("quarter"),
                "tract": row.get("tract"),
                "status": row.get("status"),
                "read_at": row.get("read_at"),
                "actuality_date": row.get("actuality_date"),
                "geom": row.get("geom"),
                "crs": row.get("crs"),
            }
            for row in rows
        ],
    )


def upsert_clearcuts(conn: Connection, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        return
    conn.execute(
        _UPSERT_CLEARCUT,
        [
            {
                "subject": row.get("subject"),
                "fgis_id": row.get("fgis_id"),
                "quarter": row.get("quarter"),
                "area": row.get("area"),
                "status": row.get("status"),
                "read_at": row.get("read_at"),
                "actuality_date": row.get("actuality_date"),
                "geom": row.get("geom"),
                "crs": row.get("crs"),
                "limitation_dt": row.get("limitation_dt"),
                "clearcut_no": row.get("clearcut_no"),
                "basis_doc_no": row.get("basis_doc_no"),
            }
            for row in rows
        ],
    )


def quarter_exists(eng: Engine, subject: str, fgis_id: str) -> bool:
    with eng.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT 1 FROM quarters
                WHERE subject = :subject AND fgis_id = :fgis_id
                """
            ),
            {"subject": subject, "fgis_id": fgis_id},
        ).first()
    return row is not None


def quarters_for_clearcut(
    conn: Connection,
    subject: str,
    *,
    audit: bool,
    period_start: date | None,
    quarter_id: str | None = None,
    full_scan: bool = False,
    today: date | None = None,
) -> list[str]:
    params: dict[str, Any] = {"subject": subject}
    not_today = (
        " AND (clearcut_polled_at IS NULL OR clearcut_polled_at < :today)"
    )
    if today is not None:
        params["today"] = today
    if quarter_id:
        sql = """
            SELECT fgis_id FROM quarters
            WHERE subject = :subject AND fgis_id = :qid
            """
        params["qid"] = quarter_id
    elif audit:
        sql = f"""
            SELECT fgis_id FROM quarters
            WHERE subject = :subject
              AND (clearcut_polled_at IS NULL OR clearcut_polled_at < :start)
              {not_today if today is not None else ""}
            ORDER BY fgis_id
            """
        params["start"] = period_start
    elif full_scan:
        sql = f"""
            SELECT fgis_id FROM quarters
            WHERE subject = :subject
              {not_today if today is not None else ""}
            ORDER BY fgis_id
            """
    else:
        sql = f"""
            SELECT fgis_id FROM quarters
            WHERE subject = :subject AND has_clearcuts
              {not_today if today is not None else ""}
            ORDER BY fgis_id
            """
    rows = conn.execute(text(sql), params)
    return [str(row[0]) for row in rows]


def stamp_clearcut_poll(
    conn: Connection,
    subject: str,
    quarter_id: str,
    *,
    polled_at: date,
    has_clearcuts: bool,
) -> None:
    stamp_clearcut_polls(
        conn,
        subject,
        [quarter_id],
        polled_at=polled_at,
        has_clearcuts=has_clearcuts,
    )


def stamp_clearcut_polls(
    conn: Connection,
    subject: str,
    quarter_ids: Sequence[str],
    *,
    polled_at: date,
    has_clearcuts: bool,
) -> None:
    if not quarter_ids:
        return
    sql = text(
        """
        UPDATE quarters
        SET clearcut_polled_at = :polled_at, has_clearcuts = :has_clearcuts
        WHERE subject = :subject AND fgis_id IN :qids
        """
    ).bindparams(bindparam("qids", expanding=True))
    unique = list(dict.fromkeys(quarter_ids))
    for offset in range(0, len(unique), _RECENT_ID_CHUNK):
        chunk = unique[offset : offset + _RECENT_ID_CHUNK]
        conn.execute(
            sql,
            {
                "subject": subject,
                "qids": chunk,
                "polled_at": polled_at,
                "has_clearcuts": has_clearcuts,
            },
        )


def recent_read_ids_subject(
    conn: Connection,
    subject: str,
    since: date,
    *,
    data_kind: str,
) -> set[str]:
    table = KIND_TABLE[data_kind]
    rows = conn.execute(
        text(
            f"""
            SELECT fgis_id FROM {table}
            WHERE subject = :subject AND read_at >= :since
            """
        ),
        {"subject": subject, "since": since},
    )
    return {str(row[0]) for row in rows}


def recent_read_ids(
    conn: Connection,
    subject: str,
    since: date,
    ids: Sequence[str],
    *,
    data_kind: str,
) -> set[str]:
    if not ids:
        return set()
    table = KIND_TABLE[data_kind]
    sql = text(
        f"""
        SELECT fgis_id FROM {table}
        WHERE subject = :subject AND read_at >= :since
          AND fgis_id IN :ids
        """
    ).bindparams(bindparam("ids", expanding=True))
    found: set[str] = set()
    unique = list(dict.fromkeys(ids))
    for offset in range(0, len(unique), _RECENT_ID_CHUNK):
        chunk = unique[offset : offset + _RECENT_ID_CHUNK]
        rows = conn.execute(
            sql,
            {"subject": subject, "since": since, "ids": chunk},
        )
        found.update(str(row[0]) for row in rows)
    return found


def write_history(
    conn: Connection,
    *,
    subject: str,
    day: date,
    result: str,
    updated_count: int,
    error: str | None,
    data_kind: str,
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
            "data_kind": data_kind,
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


_CLEARCUT_FAIL = "опрос лесосек: часть кварталов не закрыта"
_HISTORY_ERROR_MAX = 2000


def clearcut_fail_error(ids: Sequence[str]) -> str:
    unique = [str(item).strip() for item in ids if str(item).strip()]
    if not unique:
        return _CLEARCUT_FAIL
    shown: list[str] = []
    for qid in unique:
        candidate = _CLEARCUT_FAIL + "\n" + "\n".join([*shown, qid])
        rest = len(unique) - len(shown) - 1
        extra = f"\n…+{rest}" if rest > 0 else ""
        if len(candidate) + len(extra) > _HISTORY_ERROR_MAX:
            leftover = len(unique) - len(shown)
            if leftover <= 0:
                break
            return _CLEARCUT_FAIL + "\n" + "\n".join(shown) + f"\n…+{leftover}"
        shown.append(qid)
    return _CLEARCUT_FAIL + "\n" + "\n".join(shown)


def display_error(error: str | None, extra: Any = None) -> str | None:
    if isinstance(extra, (list, tuple)) and extra:
        return clearcut_fail_error(extra)
    if not error:
        return None
    if "\n" in error:
        return error
    marker = f"{_CLEARCUT_FAIL}: "
    if error.startswith(marker):
        parts = [p.strip() for p in error[len(marker) :].split(",") if p.strip()]
        if parts:
            return clearcut_fail_error(parts)
    return error


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
        "error": display_error(data.get("error")),
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
        "error": display_error(job.get("error")),
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
        "progress": progress_label(
            job.get("progress_count", updated), job.get("changed_total")
        ),
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
    def _key(subject: str, kind: str | None) -> tuple[str, str]:
        return (subject, kind or DATA_KIND)

    last_by: dict[tuple[str, str], dict[str, Any]] = {}
    for row in subjects:
        last_by.setdefault(_key(row["subject"], row.get("data_kind")), row)
    live_keys: set[tuple[str, str]] = set()
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
        key = _key(job["subject"], job.get("data_kind"))
        live_keys.add(key)
        out.append(_live_row(job, last_by.get(key)))
    for row in subjects:
        if _key(row["subject"], row.get("data_kind")) in live_keys:
            continue
        item = dict(row)
        item["in_progress"] = False
        out.append(item)
    out.sort(
        key=lambda row: (
            not row.get("in_progress"),
            row["subject"],
            row.get("data_kind") or DATA_KIND,
        )
    )
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
        SELECT DISTINCT ON (subject, data_kind)
            subject, day, result, updated_count, error, ran_at,
            period_start, period_end, data_kind
        FROM fgis_import_history
        WHERE {' AND '.join(where)}
        ORDER BY subject, data_kind, updated_count DESC, ran_at DESC, id DESC
        """
    )
    with eng.connect() as conn:
        rows = conn.execute(sql, params).mappings().all()
    return [_public_row(row) for row in rows]


def history_rows(
    eng: Engine,
    *,
    subject: str | None = None,
    data_kind: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    cap = max(1, min(limit, 500))
    params: dict[str, Any] = {"lim": cap}
    where = "TRUE"
    if data_kind:
        where += " AND data_kind = :kind"
        params["kind"] = data_kind
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
