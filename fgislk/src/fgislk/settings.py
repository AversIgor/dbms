from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import quote

import httpx
from dotenv import load_dotenv

REQUIRED_SCHEMA = "0002_constant"
KIND_QUARTERS = "quarters"
KIND_TAXATION_PIECE = "taxation_piece"
KIND_CLEARCUT = "clearcut"
DATA_KIND = KIND_TAXATION_PIECE
IMPORT_ORDER = (KIND_QUARTERS, KIND_CLEARCUT, KIND_TAXATION_PIECE)
DATA_KIND_LABELS = {
    KIND_QUARTERS: "кварталы",
    KIND_TAXATION_PIECE: "выделы",
    KIND_CLEARCUT: "лесосеки",
}
SPD_RESOURCE = {
    KIND_QUARTERS: "forestQuarter",
    KIND_TAXATION_PIECE: "taxationPiece",
    KIND_CLEARCUT: "clearcut",
}
KIND_TABLE = {
    KIND_QUARTERS: "quarters",
    KIND_TAXATION_PIECE: "taxation_piece",
    KIND_CLEARCUT: "clearcut",
}

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


def constants_url() -> str:
    load_settings()
    return os.environ.get("CONSTANTS_URL", "http://127.0.0.1:8084").rstrip("/")


def _constant(key: str):
    url = f"{constants_url()}/items/{key}"
    try:
        response = httpx.get(url, timeout=10.0)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"constants недоступен: {exc.__class__.__name__}") from exc
    if response.status_code == 404:
        raise RuntimeError(f"нет константы {key}")
    if response.status_code != 200:
        raise RuntimeError(f"constants {key}: HTTP {response.status_code}")
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(f"constants {key}: не JSON") from exc
    if not isinstance(data, dict) or "value" not in data:
        raise RuntimeError(f"constants {key}: нет value")
    return data["value"]


def fgis_host() -> str:
    raw = str(_constant("FGIS_HOST") or "").strip()
    if not raw:
        raise RuntimeError("FGIS_HOST пустой")
    return raw


def fgis_tls() -> str:
    raw = str(_constant("FGIS_TLS") or "").strip().lower()
    if raw in {"schannel", "openssl"}:
        return raw
    if raw:
        raise RuntimeError("FGIS_TLS: schannel или openssl")
    return "schannel" if sys.platform == "win32" else "openssl"


def fgis_credentials() -> tuple[str, str]:
    login = str(_constant("FGIS_LOGIN") or "").strip()
    password = str(_constant("FGIS_PASSWORD") or "")
    if not login or not password:
        raise RuntimeError("Задайте FGIS_LOGIN и FGIS_PASSWORD в константах")
    return login, password


def _positive_int(key: str) -> int:
    raw = _constant(key)
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{key} — целое ≥ 1") from exc
    if value < 1:
        raise RuntimeError(f"{key} — целое ≥ 1")
    return value


def max_workers() -> int:
    """Субъектов сразу."""
    return _positive_int("FGIS_MAX_WORKERS")


def batch_workers() -> int:
    """Параллельных пачек карточек внутри субъекта."""
    return _positive_int("FGIS_BATCH_WORKERS")


def http_workers() -> int:
    """Живых HTTP к СПД на процесс = субъекты × пачки."""
    return max_workers() * batch_workers()


def listen_port() -> int:
    load_settings()
    return int(os.environ.get("FGISLK_PORT", "8081"))
