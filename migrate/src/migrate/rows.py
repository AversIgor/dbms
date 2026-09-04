from __future__ import annotations

import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from geoalchemy2 import Geometry
from sqlalchemy import String, cast, delete, func, select

from migrate.db import engine as make_engine
from migrate.models import Base

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
MAX_DELETE_IDS = 500
DELETE_CHUNK = 1000
DELETE_BUDGET_SEC = 12.0
_SKIP_TABLES = frozenset({"constant"})


def _mappers() -> dict[str, Any]:
    return {mapper.class_.__table__.name: mapper for mapper in Base.registry.mappers}


def tables_catalog() -> list[dict[str, str]]:
    items = []
    for name, mapper in _mappers().items():
        if name in _SKIP_TABLES:
            continue
        table = mapper.class_.__table__
        items.append({"value": name, "label": table.comment or name})
    items.sort(key=lambda item: item["value"])
    return items


def _mapper(table_name: str):
    if table_name in _SKIP_TABLES:
        raise HTTPException(status_code=400, detail="нет такой таблицы")
    mapper = _mappers().get(table_name)
    if mapper is None:
        raise HTTPException(status_code=400, detail="нет такой таблицы")
    return mapper


def _pk_column(mapper):
    keys = list(mapper.primary_key)
    if len(keys) != 1:
        raise HTTPException(status_code=400, detail="составной ключ не поддерживается")
    return keys[0]


def _visible_columns(mapper) -> list:
    return [col for col in mapper.columns if not isinstance(col.type, Geometry)]


def _column_label(col) -> str:
    return col.comment or col.name


def _column_by_name(mapper, name: str):
    for col in _visible_columns(mapper):
        if col.name == name:
            return col
    raise HTTPException(status_code=400, detail="нет такого поля поиска")


def _serialize(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (bytes, memoryview)):
        return None
    return value


def _ilike_pattern(q: str) -> str:
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _filter(mapper, field: str | None, q: str | None):
    if not q:
        return None
    if not field:
        raise HTTPException(status_code=400, detail="укажите поле поиска")
    col = _column_by_name(mapper, field)
    return cast(col, String).ilike(_ilike_pattern(q), escape="\\")


def _coerce_id(raw: str, pk) -> Any:
    text = str(raw).strip()
    if not text:
        raise HTTPException(status_code=400, detail="пустой идентификатор")
    python_type = getattr(pk.type, "python_type", str)
    if python_type is int:
        try:
            return int(text)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="идентификатор не число") from exc
    return text


def describe_table(table_name: str) -> dict:
    mapper = _mapper(table_name)
    pk = _pk_column(mapper)
    columns = [
        {"name": col.name, "label": _column_label(col)}
        for col in _visible_columns(mapper)
    ]
    return {
        "table": table_name,
        "id_field": pk.name,
        "columns": columns,
        "search_fields": columns,
    }


def list_rows(
    table_name: str,
    field: str | None,
    q: str | None,
    page: int,
    size: int,
) -> dict:
    mapper = _mapper(table_name)
    model = mapper.class_
    pk = _pk_column(mapper)
    visible = _visible_columns(mapper)
    if page < 1:
        page = 1
    size = min(max(size, 1), MAX_PAGE_SIZE)
    where = _filter(mapper, field, q)
    count_stmt = select(func.count()).select_from(model)
    stmt = select(*visible).order_by(pk)
    if where is not None:
        count_stmt = count_stmt.where(where)
        stmt = stmt.where(where)
    stmt = stmt.offset((page - 1) * size).limit(size)
    eng = make_engine()
    try:
        with eng.connect() as conn:
            total = int(conn.execute(count_stmt).scalar_one())
            rows = []
            for row in conn.execute(stmt).mappings():
                rows.append({col.name: _serialize(row[col.name]) for col in visible})
    finally:
        eng.dispose()
    payload = describe_table(table_name)
    payload.update(
        {
            "rows": rows,
            "page": page,
            "size": size,
            "total": total,
            "pages": max(1, (total + size - 1) // size) if total else 1,
            "field": field,
            "q": q or "",
        }
    )
    return payload


def _delete_chunk(conn, model, pk, where, limit: int) -> int:
    subq = select(pk)
    if where is not None:
        subq = subq.where(where)
    result = conn.execute(delete(model).where(pk.in_(subq.limit(limit))))
    return result.rowcount or 0


def delete_rows(
    table_name: str,
    ids: list[str] | None,
    field: str | None,
    q: str | None,
    all_matching: bool,
) -> dict:
    mapper = _mapper(table_name)
    model = mapper.class_
    pk = _pk_column(mapper)
    eng = make_engine()
    try:
        if all_matching:
            where = _filter(mapper, field, q)
            deleted = 0
            done = False
            deadline = time.monotonic() + DELETE_BUDGET_SEC
            while True:
                with eng.begin() as conn:
                    n = _delete_chunk(conn, model, pk, where, DELETE_CHUNK)
                deleted += n
                if n < DELETE_CHUNK:
                    done = True
                    break
                if time.monotonic() >= deadline:
                    break
        else:
            if not ids:
                raise HTTPException(status_code=400, detail="нет идентификаторов")
            if len(ids) > MAX_DELETE_IDS:
                raise HTTPException(
                    status_code=400,
                    detail=f"за один раз не больше {MAX_DELETE_IDS}",
                )
            values = [_coerce_id(item, pk) for item in ids]
            with eng.begin() as conn:
                result = conn.execute(delete(model).where(pk.in_(values)))
                deleted = result.rowcount or 0
            done = True
    finally:
        eng.dispose()
    return {"ok": True, "deleted": deleted, "table": table_name, "done": done}
