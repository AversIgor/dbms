from __future__ import annotations

import asyncio

import httpx
from sqlalchemy.engine import Engine

from api.settings import REQUIRED_SCHEMA, migrate_url
from api.store import db_revision


class SchemaMismatch(RuntimeError):
    pass


async def wait_schema(engine: Engine, attempts: int = 30) -> str:
    url = f"{migrate_url()}/ready"
    last_error = "timeout"
    async with httpx.AsyncClient(timeout=10.0) as http:
        for _ in range(attempts):
            try:
                response = await http.get(url)
                if response.status_code != 200:
                    last_error = f"migrate /ready {response.status_code}"
                else:
                    revision = db_revision(engine)
                    if revision == REQUIRED_SCHEMA:
                        return revision
                    last_error = f"схема {revision}, нужно {REQUIRED_SCHEMA}"
            except httpx.HTTPError as exc:
                last_error = str(exc)
            await asyncio.sleep(2)
    raise SchemaMismatch(last_error)


async def migrate_ready() -> bool:
    url = f"{migrate_url()}/ready"
    try:
        async with httpx.AsyncClient(timeout=5.0) as http:
            response = await http.get(url)
            return response.status_code == 200
    except httpx.HTTPError:
        return False
