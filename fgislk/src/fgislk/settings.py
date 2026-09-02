from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

REQUIRED_SCHEMA = "0008_quarters"
KIND_QUARTERS = "quarters"
KIND_TAXATION_PIECE = "taxation_piece"
DATA_KIND = KIND_TAXATION_PIECE
IMPORT_ORDER = (KIND_QUARTERS, KIND_TAXATION_PIECE)
DATA_KIND_LABELS = {
    KIND_QUARTERS: "кварталы",
    KIND_TAXATION_PIECE: "выделы",
}
SPD_RESOURCE = {
    KIND_QUARTERS: "forestQuarter",
    KIND_TAXATION_PIECE: "taxationPiece",
}
KIND_TABLE = {
    KIND_QUARTERS: "quarters",
    KIND_TAXATION_PIECE: "taxation_piece",
}
DEFAULT_MAX_WORKERS = 5
DEFAULT_BATCH_WORKERS = 3
ALLOWED_SETTINGS = (
    "FGIS_MAX_WORKERS",
    "FGIS_BATCH_WORKERS",
    "FGIS_TLS",
    "FGIS_HOST",
)
_SECRET_KEYS = frozenset(
    {
        "FGIS_LOGIN",
        "FGIS_PASSWORD",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
    }
)

_DB_KEYS = (
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
)

_loaded = False
_overlay: dict[str, str] = {}
_overlay_loaded = False


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
    refresh_overlay()


def overlay_file() -> Path:
    load_settings()
    raw = os.environ.get("FGISLK_SETTINGS_FILE", "").strip()
    if raw:
        return Path(raw)
    return Path.cwd() / "fgislk-settings.json"


def refresh_overlay() -> None:
    global _overlay, _overlay_loaded
    raw = os.environ.get("FGISLK_SETTINGS_FILE", "").strip()
    path = Path(raw) if raw else Path.cwd() / "fgislk-settings.json"
    _overlay = {}
    _overlay_loaded = True
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    for key in ALLOWED_SETTINGS:
        if key not in data:
            continue
        value = data[key]
        if value is None:
            continue
        _overlay[key] = str(value).strip()


def _effective(key: str) -> str | None:
    load_settings()
    if key in _overlay:
        return _overlay[key]
    raw = os.environ.get(key)
    return raw


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
    url = os.environ.get("MIGRATE_URL", "http://127.0.0.1:8080").rstrip("/")
    return url


def fgis_host() -> str:
    raw = (_effective("FGIS_HOST") or "fgislk.gov.ru").strip()
    return raw or "fgislk.gov.ru"


def fgis_tls() -> str:
    """schannel — Windows curl.exe; openssl — Linux curl + gost-engine. Пусто — по ОС."""
    raw = (_effective("FGIS_TLS") or "").strip().lower()
    if raw in {"schannel", "openssl"}:
        return raw
    if raw:
        raise RuntimeError("FGIS_TLS: schannel или openssl")
    return "schannel" if sys.platform == "win32" else "openssl"


def fgis_credentials() -> tuple[str, str]:
    load_settings()
    login = os.environ.get("FGIS_LOGIN", "").strip()
    password = os.environ.get("FGIS_PASSWORD", "")
    if not login or not password:
        raise RuntimeError("Задайте FGIS_LOGIN и FGIS_PASSWORD в .env")
    return login, password


def _positive_int(key: str, default: int) -> int:
    raw = _effective(key) or str(default)
    try:
        value = int(raw)
    except ValueError:
        value = default
    return max(1, value)


def max_workers() -> int:
    """Субъектов сразу. По умолчанию 5."""
    return _positive_int("FGIS_MAX_WORKERS", DEFAULT_MAX_WORKERS)


def batch_workers() -> int:
    """Параллельных пачек карточек внутри субъекта. По умолчанию 3."""
    return _positive_int("FGIS_BATCH_WORKERS", DEFAULT_BATCH_WORKERS)


def http_workers() -> int:
    """Живых HTTP к СПД на процесс = субъекты × пачки."""
    return max_workers() * batch_workers()


def listen_port() -> int:
    load_settings()
    return int(os.environ.get("FGISLK_PORT", "8081"))


def _source(key: str) -> str:
    if key in _overlay:
        return "overlay"
    if os.environ.get(key):
        return "env"
    return "default"


def settings_view() -> dict:
    load_settings()
    values = {
        "FGIS_MAX_WORKERS": {
            "value": max_workers(),
            "source": _source("FGIS_MAX_WORKERS"),
        },
        "FGIS_BATCH_WORKERS": {
            "value": batch_workers(),
            "source": _source("FGIS_BATCH_WORKERS"),
        },
        "FGIS_TLS": {"value": fgis_tls(), "source": _source("FGIS_TLS")},
        "FGIS_HOST": {"value": fgis_host(), "source": _source("FGIS_HOST")},
    }
    return {"writable": True, "values": values}


def _validate_updates(payload: dict) -> dict[str, str | None]:
    if not isinstance(payload, dict):
        raise ValueError("тело — объект JSON")
    updates: dict[str, str | None] = {}
    for key, value in payload.items():
        if key in _SECRET_KEYS or key.startswith("POSTGRES_"):
            raise ValueError(f"ключ {key} менять нельзя")
        if key not in ALLOWED_SETTINGS:
            raise ValueError(f"ключ {key} не из allowlist")
        if value is None:
            updates[key] = None
            continue
        text = str(value).strip()
        if key in ("FGIS_MAX_WORKERS", "FGIS_BATCH_WORKERS"):
            try:
                number = int(text)
            except ValueError as exc:
                raise ValueError(f"{key} — целое ≥ 1") from exc
            if number < 1:
                raise ValueError(f"{key} — целое ≥ 1")
            updates[key] = str(number)
        elif key == "FGIS_TLS":
            lowered = text.lower()
            if lowered not in {"schannel", "openssl"}:
                raise ValueError("FGIS_TLS: schannel или openssl")
            updates[key] = lowered
        else:
            if not text:
                raise ValueError("FGIS_HOST пустой")
            if any(ch.isspace() for ch in text):
                raise ValueError("FGIS_HOST без пробелов")
            updates[key] = text
    return updates


def apply_settings(payload: dict) -> dict:
    load_settings()
    updates = _validate_updates(payload)
    global _overlay
    merged = dict(_overlay)
    for key, value in updates.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    path = overlay_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _overlay = merged
    return settings_view()
