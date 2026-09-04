from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

REQUIRED_SCHEMA = "0003_api_indexes"

_DB_KEYS = (
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
)

_loaded = False


def load_settings() -> None:
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


def migrate_url() -> str:
    load_settings()
    return os.environ.get("MIGRATE_URL", "http://127.0.0.1:8080").rstrip("/")


def listen_port() -> int:
    load_settings()
    return int(os.environ.get("API_PORT", "8083"))
