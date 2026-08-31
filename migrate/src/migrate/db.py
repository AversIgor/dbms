from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

_DB_KEYS = (
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
)

_loaded = False


def load_settings() -> None:
    """Читает корневой .env, не перезаписывая уже заданные переменные (Compose)."""
    global _loaded
    if _loaded:
        return
    explicit = os.environ.get("ENV_FILE")
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    cwd = Path.cwd()
    candidates.extend(folder / ".env" for folder in (cwd, *cwd.parents))
    here = Path(__file__).resolve()
    candidates.extend(folder / ".env" for folder in here.parents)
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen or not candidate.is_file():
            continue
        seen.add(resolved)
        load_dotenv(candidate, override=False)
        break
    _loaded = True


def _require_db_env() -> dict[str, str]:
    load_settings()
    missing = [key for key in _DB_KEYS if not os.environ.get(key)]
    if missing:
        raise RuntimeError(
            "Нет настроек БД: "
            + ", ".join(missing)
            + ". Задайте их в .env в корне репозитория."
        )
    return {key: os.environ[key] for key in _DB_KEYS}


def database_url() -> str:
    settings = _require_db_env()
    user = quote(settings["POSTGRES_USER"], safe="")
    password = quote(settings["POSTGRES_PASSWORD"], safe="")
    host = settings["POSTGRES_HOST"]
    port = settings["POSTGRES_PORT"]
    db = settings["POSTGRES_DB"]
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"


def psycopg_dsn() -> str:
    return database_url().replace("postgresql+psycopg://", "postgresql://", 1)


def parsed_dsn() -> tuple[str, int, str, str]:
    settings = _require_db_env()
    return (
        settings["POSTGRES_HOST"],
        int(settings["POSTGRES_PORT"]),
        settings["POSTGRES_USER"],
        settings["POSTGRES_DB"],
    )


def alembic_ini_path() -> Path:
    env = os.environ.get("ALEMBIC_INI")
    if env:
        return Path(env)
    cwd = Path.cwd() / "alembic.ini"
    if cwd.is_file():
        return cwd
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "alembic.ini"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("alembic.ini не найден (задайте ALEMBIC_INI)")


def alembic_config() -> Config:
    ini = alembic_ini_path()
    cfg = Config(str(ini))
    cfg.set_main_option("sqlalchemy.url", database_url())
    cfg.set_main_option("script_location", str(ini.parent / "alembic"))
    src = ini.parent / "src"
    if src.is_dir():
        cfg.set_main_option("prepend_sys_path", str(src))
    return cfg


def engine() -> Engine:
    return create_engine(database_url(), pool_pre_ping=True)
