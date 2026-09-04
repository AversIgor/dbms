from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import bindparam, create_engine, inspect as sa_inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from api.settings import database_url


def make_engine() -> Engine:
    return create_engine(database_url(), pool_pre_ping=True, pool_size=5, max_overflow=2)


def db_revision(eng: Engine) -> str | None:
    try:
        with eng.connect() as conn:
            if not sa_inspect(conn).has_table("alembic_version"):
                return None
            row = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            return str(row) if row else None
    except SQLAlchemyError:
        return None


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def list_quarters(
    eng: Engine,
    *,
    subforestry: str,
    tract: str | None,
    has_clearcuts_only: bool,
) -> list[dict[str, Any]]:
    sql = """
        SELECT fgis_id, quarter, tract, actuality_date, read_at, has_clearcuts, status
        FROM quarters
        WHERE subforestry = :subforestry
    """
    params: dict[str, Any] = {"subforestry": subforestry}
    if tract is not None:
        sql += " AND tract = :tract"
        params["tract"] = tract
    if has_clearcuts_only:
        sql += " AND has_clearcuts"
    with eng.connect() as conn:
        rows = conn.execute(text(sql), params)
        return [
            {
                "fgis_id": row.fgis_id,
                "quarter": row.quarter,
                "tract": row.tract,
                "actuality_date": _iso(row.actuality_date),
                "read_at": _iso(row.read_at),
                "has_clearcuts": row.has_clearcuts,
                "status": row.status,
            }
            for row in rows
        ]


def _area(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError, InvalidOperation):
        return 0.0


def _quarter_plain(value: str) -> str:
    text = value.strip().replace("\xa0", "").replace(" ", "")
    if text.isdigit():
        return str(int(text))
    return value.strip()


def _piece_of_quarter_sql(alias: str) -> str:
    # 1С: выдел.НомерКварталаФГИСЛК = квартал.КодФГИСЛК.
    # У нас taxation_piece.quarter — forestQuarterRegistrationNo (номер или учётный).
    return f"""
        ({alias}.quarter = q.fgis_id
         OR ({alias}.quarter = q.quarter AND {alias}.subject = q.subject))
    """


def _clearcut_of_quarter_sql(alias: str) -> str:
    return f"""
        ({alias}.quarter = q.fgis_id
         OR ({alias}.quarter = q.quarter AND {alias}.subject = q.subject))
    """


def _in_ids(sql: str):
    return text(sql).bindparams(bindparam("ids", expanding=True))


def list_tracts(eng: Engine, *, subforestry: str) -> list[dict[str, str | None]]:
    sql = """
        SELECT DISTINCT tract
        FROM quarters
        WHERE subforestry = :subforestry
        ORDER BY tract
    """
    with eng.connect() as conn:
        return [
            {"tract": row.tract}
            for row in conn.execute(text(sql), {"subforestry": subforestry})
        ]


def list_tracts_of_quarter(
    eng: Engine, *, subforestry: str, quarter: str
) -> list[dict[str, str | None]]:
    sql = """
        SELECT DISTINCT tract
        FROM quarters
        WHERE subforestry = :subforestry
          AND quarter = :quarter
        ORDER BY tract
    """
    with eng.connect() as conn:
        return [
            {"tract": row.tract}
            for row in conn.execute(
                text(sql),
                {"subforestry": subforestry, "quarter": _quarter_plain(quarter)},
            )
        ]


def quarter_card(eng: Engine, *, fgis_ids: list[str]) -> dict[str, Any]:
    piece_sql = f"""
        SELECT quarter_fgis_id, fgis_id, taxation_piece, area, read_at,
               actuality_date, status
        FROM (
            SELECT q.fgis_id AS quarter_fgis_id, tp.fgis_id, tp.taxation_piece,
                   tp.area, tp.read_at, tp.actuality_date, tp.status
            FROM quarters q
            JOIN taxation_piece tp ON {_piece_of_quarter_sql("tp")}
            WHERE q.fgis_id IN :ids
            UNION
            SELECT tp.quarter, tp.fgis_id, tp.taxation_piece, tp.area, tp.read_at,
                   tp.actuality_date, tp.status
            FROM taxation_piece tp
            WHERE tp.quarter IN :ids
        ) pieces
        ORDER BY actuality_date
    """
    cut_sql = f"""
        SELECT quarter_fgis_id, fgis_id, clearcut_no, area, status, limitation_dt,
               basis_doc_no, read_at, actuality_date
        FROM (
            SELECT q.fgis_id AS quarter_fgis_id, c.fgis_id, c.clearcut_no, c.area,
                   c.status, c.limitation_dt, c.basis_doc_no, c.read_at,
                   c.actuality_date
            FROM quarters q
            JOIN clearcut c ON {_clearcut_of_quarter_sql("c")}
            WHERE q.fgis_id IN :ids
            UNION
            SELECT c.quarter, c.fgis_id, c.clearcut_no, c.area, c.status,
                   c.limitation_dt, c.basis_doc_no, c.read_at, c.actuality_date
            FROM clearcut c
            WHERE c.quarter IN :ids
        ) cuts
        ORDER BY actuality_date
    """
    params = {"ids": fgis_ids}
    with eng.connect() as conn:
        pieces = conn.execute(_in_ids(piece_sql), params)
        cuts = conn.execute(_in_ids(cut_sql), params)
        taxation_pieces = [
            {
                "quarter_fgis_id": row.quarter_fgis_id,
                "fgis_id": row.fgis_id,
                "taxation_piece": row.taxation_piece,
                "area": _area(row.area),
                "read_at": _iso(row.read_at),
                "actuality_date": _iso(row.actuality_date),
                "status": row.status,
            }
            for row in pieces
        ]
        clearcuts = [
            {
                "quarter_fgis_id": row.quarter_fgis_id,
                "fgis_id": row.fgis_id,
                "clearcut_no": row.clearcut_no,
                "area": _area(row.area),
                "status": row.status,
                "limitation_dt": _iso(row.limitation_dt),
                "basis_doc_no": row.basis_doc_no,
                "read_at": _iso(row.read_at),
                "actuality_date": _iso(row.actuality_date),
            }
            for row in cuts
        ]
    return {
        "taxation_pieces": taxation_pieces,
        "clearcuts": clearcuts,
        "history": [],
    }


def quarter_props(eng: Engine, *, fgis_id: str) -> dict[str, Any]:
    sql = """
        SELECT fgis_id, subject, subforestry, quarter, tract
        FROM quarters
        WHERE fgis_id = :fgis_id
    """
    with eng.connect() as conn:
        row = conn.execute(text(sql), {"fgis_id": fgis_id}).first()
    if row is None:
        return {}
    return {
        "fgis_id": row.fgis_id,
        "subject": row.subject,
        "subforestry": row.subforestry,
        "quarter": row.quarter,
        "tract": row.tract,
    }


def _location_row(row: Any) -> dict[str, Any]:
    return {
        "quarter": row.quarter,
        "tract": row.tract,
        "subforestry": row.subforestry,
        "taxation_piece": row.taxation_piece,
        "area": _area(row.area) if row.area is not None else 0.0,
        "taxation_piece_fgis_id": row.taxation_piece_fgis_id or "",
        "quarter_fgis_id": row.quarter_fgis_id or "",
        "actuality_date": _iso(row.actuality_date),
        "status": row.status,
    }


def _sort_location(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def piece_num(item: dict[str, Any]) -> int:
        raw = str(item.get("taxation_piece") or "")
        try:
            return int(raw)
        except ValueError:
            return 0

    rows.sort(key=lambda item: item.get("actuality_date") or "", reverse=True)
    rows.sort(key=piece_num)
    return rows


def location_by_fgis_id(eng: Engine, *, fgis_id: str) -> list[dict[str, Any]]:
    exists_q = "SELECT 1 FROM quarters WHERE fgis_id = :fgis_id"
    exists_p = "SELECT 1 FROM taxation_piece WHERE fgis_id = :fgis_id"
    piece_sql = f"""
        SELECT COALESCE(q.quarter, '') AS quarter,
               COALESCE(q.tract, '') AS tract,
               COALESCE(q.subforestry, '') AS subforestry,
               tp.taxation_piece AS taxation_piece,
               tp.area AS area,
               tp.fgis_id AS taxation_piece_fgis_id,
               COALESCE(q.fgis_id, '') AS quarter_fgis_id,
               tp.actuality_date AS actuality_date,
               tp.status AS status
        FROM taxation_piece tp
        LEFT JOIN quarters q ON {_piece_of_quarter_sql("tp")}
        WHERE tp.fgis_id = :fgis_id
        ORDER BY tp.actuality_date DESC NULLS LAST
    """
    quarter_sql = f"""
        SELECT q.quarter AS quarter,
               q.tract AS tract,
               q.subforestry AS subforestry,
               COALESCE(tp.taxation_piece, '') AS taxation_piece,
               COALESCE(tp.area, 0) AS area,
               COALESCE(tp.fgis_id, '') AS taxation_piece_fgis_id,
               q.fgis_id AS quarter_fgis_id,
               tp.actuality_date AS actuality_date,
               tp.status AS status
        FROM quarters q
        LEFT JOIN taxation_piece tp ON {_piece_of_quarter_sql("tp")}
        WHERE q.fgis_id = :fgis_id
        ORDER BY q.actuality_date DESC NULLS LAST,
                 tp.actuality_date DESC NULLS LAST
    """
    params = {"fgis_id": fgis_id}
    with eng.connect() as conn:
        as_piece = conn.execute(text(exists_p), params).first() is not None
        as_quarter = conn.execute(text(exists_q), params).first() is not None
        if as_piece:
            rows = list(conn.execute(text(piece_sql), params))
        elif as_quarter:
            rows = list(conn.execute(text(quarter_sql), params))
        else:
            return []
    return _sort_location([_location_row(row) for row in rows])


def location_by_subforestry_and_quarter(
    eng: Engine, *, subforestry: str, quarter: str
) -> list[dict[str, Any]]:
    sql = """
        SELECT DISTINCT fgis_id, subforestry, quarter, tract, status, actuality_date
        FROM quarters
        WHERE subforestry = :subforestry
          AND quarter = :quarter
        ORDER BY actuality_date DESC NULLS LAST
    """
    params = {
        "subforestry": subforestry,
        "quarter": _quarter_plain(quarter),
    }
    with eng.connect() as conn:
        rows = conn.execute(text(sql), params)
        return [
            {
                "fgis_id": row.fgis_id,
                "subforestry": row.subforestry,
                "quarter": row.quarter,
                "tract": row.tract,
                "status": row.status,
            }
            for row in rows
        ]


def quarter_fgis_id(
    eng: Engine, *, subforestry: str, tract: str, quarter: str
) -> str:
    sql = """
        SELECT fgis_id
        FROM quarters
        WHERE subforestry = :subforestry
          AND quarter = :quarter
          AND COALESCE(tract, '') LIKE :tract
        ORDER BY actuality_date DESC NULLS LAST
        LIMIT 1
    """
    params = {
        "subforestry": subforestry,
        "quarter": _quarter_plain(quarter),
        "tract": tract.strip(),
    }
    with eng.connect() as conn:
        value = conn.execute(text(sql), params).scalar()
    return str(value) if value else ""


def taxation_piece_fgis_id(
    eng: Engine, *, quarter_fgis_id: str, taxation_piece: str
) -> str:
    sql = f"""
        SELECT tp.fgis_id
        FROM taxation_piece tp
        JOIN quarters q ON q.fgis_id = :qid AND {_piece_of_quarter_sql("tp")}
        WHERE tp.taxation_piece = :piece
        ORDER BY tp.read_at DESC NULLS LAST, tp.actuality_date DESC NULLS LAST
        LIMIT 1
    """
    params = {"qid": quarter_fgis_id, "piece": str(taxation_piece).strip()}
    with eng.connect() as conn:
        value = conn.execute(text(sql), params).scalar()
        if value:
            return str(value)
        fallback = conn.execute(
            text(
                """
                SELECT fgis_id
                FROM taxation_piece
                WHERE quarter = :qid AND taxation_piece = :piece
                ORDER BY read_at DESC NULLS LAST, actuality_date DESC NULLS LAST
                LIMIT 1
                """
            ),
            params,
        ).scalar()
    return str(fallback) if fallback else ""


def clearcut_fgis_id(
    eng: Engine,
    *,
    quarter_fgis_id: str,
    clearcut_no: str,
    area: Decimal,
) -> str:
    sql = f"""
        SELECT c.fgis_id
        FROM clearcut c
        JOIN quarters q ON q.fgis_id = :qid AND {_clearcut_of_quarter_sql("c")}
        WHERE c.clearcut_no = :no AND c.area = :area
        LIMIT 1
    """
    params = {"qid": quarter_fgis_id, "no": str(clearcut_no).strip(), "area": area}
    with eng.connect() as conn:
        value = conn.execute(text(sql), params).scalar()
        if value:
            return str(value)
        fallback = conn.execute(
            text(
                """
                SELECT fgis_id
                FROM clearcut
                WHERE quarter = :qid AND clearcut_no = :no AND area = :area
                LIMIT 1
                """
            ),
            params,
        ).scalar()
    return str(fallback) if fallback else ""


def list_clearcuts(eng: Engine, *, quarter_fgis_id: str) -> list[dict[str, Any]]:
    sql = f"""
        SELECT c.fgis_id, c.clearcut_no, c.area, c.status, c.basis_doc_no
        FROM clearcut c
        JOIN quarters q ON q.fgis_id = :qid AND {_clearcut_of_quarter_sql("c")}
    """
    params = {"qid": quarter_fgis_id}
    with eng.connect() as conn:
        rows = list(conn.execute(text(sql), params))
        if not rows:
            rows = list(
                conn.execute(
                    text(
                        """
                        SELECT fgis_id, clearcut_no, area, status, basis_doc_no
                        FROM clearcut
                        WHERE quarter = :qid
                        """
                    ),
                    params,
                )
            )
    return [
        {
            "fgis_id": row.fgis_id,
            "clearcut_no": row.clearcut_no,
            "area": _area(row.area) if row.area is not None else 0.0,
            "basis_doc_no": row.basis_doc_no,
            "status": row.status,
        }
        for row in rows
    ]


def clearcut_props(eng: Engine, *, fgis_id: str) -> dict[str, Any]:
    sql = f"""
        SELECT c.fgis_id, c.clearcut_no, c.area, c.quarter AS clearcut_quarter,
               q.subforestry, q.quarter, q.tract, q.fgis_id AS quarter_fgis_id
        FROM clearcut c
        LEFT JOIN LATERAL (
            SELECT q.fgis_id, q.subforestry, q.quarter, q.tract
            FROM quarters q
            WHERE {_clearcut_of_quarter_sql("c")}
            ORDER BY CASE WHEN q.fgis_id = c.quarter THEN 0 ELSE 1 END
            LIMIT 1
        ) q ON true
        WHERE c.fgis_id = :fgis_id
    """
    with eng.connect() as conn:
        row = conn.execute(text(sql), {"fgis_id": fgis_id}).first()
    if row is None:
        return {}
    return {
        "fgis_id": row.fgis_id,
        "clearcut_no": row.clearcut_no,
        "area": _area(row.area) if row.area is not None else 0.0,
        "subforestry": row.subforestry or "",
        "quarter": row.quarter or "",
        "quarter_fgis_id": row.quarter_fgis_id or row.clearcut_quarter or "",
        "tract": row.tract or "",
    }
