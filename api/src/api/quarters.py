from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from api.store import list_quarters

ALL_TRACTS = "ВСЕ_УРОЧИЩА"

router = APIRouter()


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@router.get("/getListQuarters")
def get_list_quarters(
    request: Request,
    subforestry: str = Query(),
    tract: str | None = Query(default=None),
    has_clearcuts: str | None = Query(default=None),
):
    code = (subforestry or "").strip()
    if not code:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "нужен subforestry"},
        )
    tract_value = (tract or "").strip()
    if tract_value == "" or tract_value == ALL_TRACTS:
        tract_value = None
    rows = list_quarters(
        request.app.state.engine,
        subforestry=code,
        tract=tract_value,
        has_clearcuts_only=_truthy(has_clearcuts),
    )
    return rows
