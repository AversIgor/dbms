from __future__ import annotations

from decimal import Decimal, InvalidOperation

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from api.settings import fgislk_url
from api.store import (
    clearcut_fgis_id,
    clearcut_props,
    list_clearcuts,
    list_quarters,
    list_tracts,
    list_tracts_of_quarter,
    location_by_fgis_id,
    location_by_subforestry_and_quarter,
    quarter_card,
    quarter_fgis_id,
    quarter_props,
    taxation_piece_fgis_id,
)

ALL_TRACTS = "ВСЕ_УРОЧИЩА"

router = APIRouter()


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _need(name: str, value: str | None) -> str | JSONResponse:
    text = (value or "").strip()
    if not text:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": f"нужен {name}"},
        )
    return text


def _fgis_ids(values: list[str]) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for raw in values:
        for part in raw.split(","):
            item = part.strip()
            if not item or item in seen:
                continue
            seen.add(item)
            ids.append(item)
    return ids


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


@router.get("/getListTracts")
def get_list_tracts(request: Request, subforestry: str = Query()):
    code = _need("subforestry", subforestry)
    if isinstance(code, JSONResponse):
        return code
    return list_tracts(request.app.state.engine, subforestry=code)


@router.get("/getListTractsOfQuarter")
def get_list_tracts_of_quarter(
    request: Request,
    subforestry: str = Query(),
    quarter: str = Query(),
):
    code = _need("subforestry", subforestry)
    if isinstance(code, JSONResponse):
        return code
    number = _need("quarter", quarter)
    if isinstance(number, JSONResponse):
        return number
    return list_tracts_of_quarter(
        request.app.state.engine, subforestry=code, quarter=number
    )


@router.get("/getQuarterCard")
def get_quarter_card(
    request: Request,
    fgis_id: list[str] = Query(default=[]),
):
    ids = _fgis_ids(fgis_id)
    if not ids:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "нужен fgis_id"},
        )
    return quarter_card(request.app.state.engine, fgis_ids=ids)


@router.get("/getQuarterProps")
def get_quarter_props(request: Request, fgis_id: str = Query()):
    code = _need("fgis_id", fgis_id)
    if isinstance(code, JSONResponse):
        return code
    return quarter_props(request.app.state.engine, fgis_id=code)


@router.get("/getLocation")
def get_location(request: Request, fgis_id: str = Query()):
    code = _need("fgis_id", fgis_id)
    if isinstance(code, JSONResponse):
        return code
    return location_by_fgis_id(request.app.state.engine, fgis_id=code)


@router.get("/getLocationBySubforestryAndQuarter")
def get_location_by_subforestry_and_quarter(
    request: Request,
    subforestry: str = Query(),
    quarter: str = Query(),
):
    code = _need("subforestry", subforestry)
    if isinstance(code, JSONResponse):
        return code
    number = _need("quarter", quarter)
    if isinstance(number, JSONResponse):
        return number
    return location_by_subforestry_and_quarter(
        request.app.state.engine, subforestry=code, quarter=number
    )


@router.get("/getQuarterFgisId")
def get_quarter_fgis_id(
    request: Request,
    subforestry: str = Query(),
    quarter: str = Query(),
    tract: str | None = Query(default=None),
):
    code = _need("subforestry", subforestry)
    if isinstance(code, JSONResponse):
        return code
    number = _need("quarter", quarter)
    if isinstance(number, JSONResponse):
        return number
    return quarter_fgis_id(
        request.app.state.engine,
        subforestry=code,
        tract=(tract or "").strip(),
        quarter=number,
    )


@router.get("/getTaxationPieceFgisId")
def get_taxation_piece_fgis_id(
    request: Request,
    quarter_fgis_id: str = Query(),
    taxation_piece: str = Query(),
):
    qid = _need("quarter_fgis_id", quarter_fgis_id)
    if isinstance(qid, JSONResponse):
        return qid
    piece = _need("taxation_piece", taxation_piece)
    if isinstance(piece, JSONResponse):
        return piece
    return taxation_piece_fgis_id(
        request.app.state.engine, quarter_fgis_id=qid, taxation_piece=piece
    )


@router.get("/getClearcutFgisId")
def get_clearcut_fgis_id(
    request: Request,
    quarter_fgis_id: str = Query(),
    clearcut_no: str = Query(),
    area: str = Query(),
):
    qid = _need("quarter_fgis_id", quarter_fgis_id)
    if isinstance(qid, JSONResponse):
        return qid
    number = _need("clearcut_no", clearcut_no)
    if isinstance(number, JSONResponse):
        return number
    raw = (area or "").strip().replace(",", ".")
    if not raw:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "нужен area"},
        )
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "area — число"},
        )
    return clearcut_fgis_id(
        request.app.state.engine,
        quarter_fgis_id=qid,
        clearcut_no=number,
        area=amount,
    )


@router.get("/getListClearcuts")
def get_list_clearcuts(request: Request, quarter_fgis_id: str = Query()):
    qid = _need("quarter_fgis_id", quarter_fgis_id)
    if isinstance(qid, JSONResponse):
        return qid
    return list_clearcuts(request.app.state.engine, quarter_fgis_id=qid)


@router.get("/updateListCuttingAreaByQuarter")
async def update_list_cutting_area_by_quarter(fgis_id: str | None = Query(default=None)):
    code = _need("fgis_id", fgis_id)
    if isinstance(code, JSONResponse):
        return code
    url = f"{fgislk_url()}/updateListCuttingAreaByQuarter"
    try:
        async with httpx.AsyncClient(timeout=20.0) as http:
            response = await http.get(url, params={"fgis_id": code})
    except httpx.HTTPError as exc:
        return JSONResponse(
            status_code=503,
            content={"ok": False, "error": f"fgislk недоступен: {exc}"},
        )
    try:
        body = response.json()
    except ValueError:
        body = {"ok": False, "error": "fgislk: не JSON"}
    return JSONResponse(status_code=response.status_code, content=body)


@router.get("/getClearcutProps")
def get_clearcut_props(request: Request, fgis_id: str = Query()):
    code = _need("fgis_id", fgis_id)
    if isinstance(code, JSONResponse):
        return code
    return clearcut_props(request.app.state.engine, fgis_id=code)
