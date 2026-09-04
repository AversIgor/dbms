from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import create_engine, inspect as sa_inspect, text
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
