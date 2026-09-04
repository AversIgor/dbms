from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

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


def listen_port() -> int:
    load_settings()
    return int(os.environ.get("ADMIN_PORT", "8082"))


def migrate_url() -> str:
    load_settings()
    return os.environ.get("MIGRATE_URL", "http://127.0.0.1:8080").rstrip("/")


def fgislk_url() -> str:
    load_settings()
    return os.environ.get("FGISLK_URL", "http://127.0.0.1:8081").rstrip("/")


def api_url() -> str:
    load_settings()
    return os.environ.get("API_URL", "http://127.0.0.1:8083").rstrip("/")


def constants_url() -> str:
    load_settings()
    return os.environ.get("CONSTANTS_URL", "http://127.0.0.1:8084").rstrip("/")
