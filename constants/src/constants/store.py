from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine, inspect as sa_inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from constants.settings import database_url
from constants.types import ConstantTypeError, to_json_value, to_stored


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


def _item(row: Any) -> dict[str, Any]:
    return {
        "key": row.key,
        "kind": row.kind,
        "value": to_json_value(row.kind, row.value),
        "title": row.title,
    }


def list_items(eng: Engine) -> list[dict[str, Any]]:
    sql = "SELECT key, kind, value, title FROM constant ORDER BY key"
    with eng.connect() as conn:
        return [_item(row) for row in conn.execute(text(sql))]


def get_item(eng: Engine, key: str) -> dict[str, Any] | None:
    sql = "SELECT key, kind, value, title FROM constant WHERE key = :key"
    with eng.connect() as conn:
        row = conn.execute(text(sql), {"key": key}).first()
    if row is None:
        return None
    return _item(row)


def put_item(eng: Engine, key: str, raw: Any) -> dict[str, Any]:
    sql = "SELECT key, kind, value, title FROM constant WHERE key = :key"
    with eng.begin() as conn:
        row = conn.execute(text(sql), {"key": key}).first()
        if row is None:
            raise KeyError(key)
        stored = to_stored(row.kind, raw)
        conn.execute(
            text("UPDATE constant SET value = :value WHERE key = :key"),
            {"value": stored, "key": key},
        )
        row = conn.execute(text(sql), {"key": key}).one()
    return _item(row)


__all__ = [
    "ConstantTypeError",
    "db_revision",
    "get_item",
    "list_items",
    "make_engine",
    "put_item",
]
