from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from admin import __version__
from admin.catalog import public_catalog, section_by_id
from admin.proxy import proxy_url

STATIC = Path(__file__).resolve().parent / "static"
ALLOWED_METHODS = frozenset({"GET", "PUT", "POST", "PATCH", "HEAD"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = httpx.AsyncClient(timeout=20.0, follow_redirects=False)
    app.state.http = client
    yield
    await client.aclose()


app = FastAPI(title="admin", version=__version__, lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/catalog")
def catalog_endpoint() -> dict:
    return {"sections": public_catalog()}


@app.api_route(
    "/p/{section_id}/{path:path}",
    methods=["GET", "PUT", "POST", "PATCH", "HEAD"],
)
async def proxy(section_id: str, path: str, request: Request):
    if request.method not in ALLOWED_METHODS:
        return JSONResponse(status_code=405, content={"ok": False, "error": "метод"})
    section = section_by_id(section_id)
    if section is None:
        return JSONResponse(
            status_code=404, content={"ok": False, "error": "нет раздела"}
        )
    base = section.get("base_url")
    if not base:
        return JSONResponse(
            status_code=404, content={"ok": False, "error": "у раздела нет HTTP"}
        )
    target = proxy_url(base, path, request.url.query)
    if target is None:
        return JSONResponse(
            status_code=400, content={"ok": False, "error": "путь нельзя проксировать"}
        )
    headers = {}
    content_type = request.headers.get("content-type")
    if content_type:
        headers["content-type"] = content_type
    body = await request.body()
    client: httpx.AsyncClient = app.state.http
    try:
        upstream = await client.request(
            request.method,
            target,
            headers=headers,
            content=body if body else None,
        )
    except httpx.RequestError as exc:
        return JSONResponse(
            status_code=502,
            content={"ok": False, "error": f"раздел недоступен: {exc.__class__.__name__}"},
        )
    media = upstream.headers.get("content-type")
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=media,
    )


if STATIC.is_dir():
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
