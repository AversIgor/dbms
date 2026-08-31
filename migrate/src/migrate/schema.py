from __future__ import annotations

import shutil
import subprocess
import time

import psycopg
from alembic import command
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect as sa_inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from migrate.db import alembic_config, engine as make_engine, parsed_dsn, psycopg_dsn
from migrate.state import record_upgrade


def wait_for_db(timeout: int = 60) -> None:
    host, port, user, db = parsed_dsn()
    deadline = time.monotonic() + timeout
    last_error = "timeout"
    while time.monotonic() < deadline:
        if shutil.which("pg_isready"):
            result = subprocess.run(
                ["pg_isready", "-h", host, "-p", str(port), "-U", user, "-d", db],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return
            last_error = result.stdout.strip() or result.stderr.strip() or "pg_isready failed"
        else:
            try:
                with psycopg.connect(psycopg_dsn(), connect_timeout=3) as conn:
                    conn.execute("SELECT 1")
                return
            except Exception as exc:  # noqa: BLE001 — ждём любую ошибку сети/аутентификации
                last_error = str(exc)
        time.sleep(1)
    raise RuntimeError(f"БД не готова за {timeout} с: {last_error}")


def revision_history() -> list[dict]:
    script = ScriptDirectory.from_config(alembic_config())
    rows = []
    for rev in script.walk_revisions():
        rows.append(
            {
                "revision": rev.revision,
                "down_revision": rev.down_revision,
                "message": (rev.doc or "").strip().split("\n", 1)[0],
            }
        )
    return rows


def head_revision() -> str | None:
    script = ScriptDirectory.from_config(alembic_config())
    return script.get_current_head()


def db_revision(eng: Engine | None = None) -> str | None:
    own = eng is None
    eng = eng or make_engine()
    try:
        with eng.connect() as conn:
            if not sa_inspect(conn).has_table("alembic_version"):
                return None
            context = MigrationContext.configure(conn)
            return context.get_current_revision()
    finally:
        if own:
            eng.dispose()


def postgis_installed(eng: Engine | None = None) -> bool:
    own = eng is None
    eng = eng or make_engine()
    try:
        with eng.connect() as conn:
            row = conn.execute(
                text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'postgis')")
            ).scalar()
            return bool(row)
    except SQLAlchemyError:
        return False
    finally:
        if own:
            eng.dispose()


def inspect_schema() -> dict:
    head = head_revision()
    eng = make_engine()
    try:
        revision = db_revision(eng)
        if revision is None:
            return {
                "database": True,
                "revision": None,
                "head": head,
                "in_sync": False,
                "postgis": postgis_installed(eng),
                "error": "нет таблицы alembic_version",
            }
        return {
            "database": True,
            "revision": revision,
            "head": head,
            "in_sync": revision == head,
            "postgis": postgis_installed(eng),
            "error": None if revision == head else "revision ≠ head",
        }
    except (SQLAlchemyError, OSError) as exc:
        return {
            "database": False,
            "revision": None,
            "head": head,
            "in_sync": False,
            "postgis": False,
            "error": str(exc),
        }
    finally:
        eng.dispose()


def run_upgrade() -> str:
    wait_for_db()
    cfg = alembic_config()
    try:
        command.upgrade(cfg, "head")
        revision = db_revision()
        record_upgrade(ok=True, message="ok", revision=revision)
        return revision or ""
    except Exception as exc:
        record_upgrade(ok=False, message=str(exc), revision=None)
        raise


def run_current() -> None:
    wait_for_db()
    command.current(alembic_config(), verbose=True)


def run_history() -> None:
    command.history(alembic_config(), indicate_current=True)


def run_downgrade(target: str) -> None:
    wait_for_db()
    command.downgrade(alembic_config(), target)


def run_revision(message: str, autogenerate: bool) -> None:
    command.revision(alembic_config(), message=message, autogenerate=autogenerate)
