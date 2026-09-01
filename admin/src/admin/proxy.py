from __future__ import annotations

from urllib.parse import unquote, urljoin, urlparse


def proxy_url(base: str, path: str, query: str = "") -> str | None:
    if not base or not path:
        return None
    path = unquote(path)
    if path.startswith("/") or "\\" in path:
        return None
    parts = path.split("/")
    if any(part == ".." or part == "." for part in parts):
        return None
    joined = urljoin(base.rstrip("/") + "/", path)
    parsed = urlparse(joined)
    origin = urlparse(base)
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.hostname != origin.hostname:
        return None
    if parsed.port != origin.port:
        return None
    if parsed.username or parsed.password:
        return None
    if query:
        return f"{joined}?{query}"
    return joined
