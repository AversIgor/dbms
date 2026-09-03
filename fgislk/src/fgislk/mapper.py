from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fgislk.settings import KIND_QUARTERS, KIND_TAXATION_PIECE
from fgislk.windows import MSK

_MS_JSON_DATE = re.compile(r"^/Date\((-?\d+)(?:[+-]\d{4})?\)/$")
_EPOCH_MS = 10_000_000_000


def _clip(value: Any, length: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:length]


def _area(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _from_epoch(raw: int | float) -> date:
    seconds = float(raw) / 1000 if abs(raw) >= _EPOCH_MS else float(raw)
    return datetime.fromtimestamp(seconds, tz=MSK).date()


def _date(value: Any) -> date | None:
    """modifyDttm СПД: ISO, epoch мс (как в 1С), /Date(ms)/."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        current = value if value.tzinfo is not None else value.replace(tzinfo=MSK)
        return current.astimezone(MSK).date()
    if isinstance(value, date):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return _from_epoch(value)
    text = str(value).strip()
    if not text:
        return None
    match = _MS_JSON_DATE.match(text)
    if match:
        return _from_epoch(int(match.group(1)))
    if text.isdigit() or (text[0] == "-" and text[1:].isdigit()):
        return _from_epoch(int(text))
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=MSK)
    return parsed.astimezone(MSK).date()


def _coord(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return format(number, ".15g")


def _ring_wkt(points: list[Any]) -> str | None:
    ordered = sorted(
        (p for p in points if isinstance(p, dict)),
        key=lambda p: (p.get("pointNumber") is None, p.get("pointNumber") or 0),
    )
    coords: list[str] = []
    for point in ordered:
        x = _coord(point.get("longitude"))
        y = _coord(point.get("latitude"))
        if x is None or y is None:
            continue
        coords.append(f"{x} {y}")
    if len(coords) < 3:
        return None
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    if len(coords) < 4:
        return None
    return "(" + ", ".join(coords) + ")"


def _area_blob(payload: dict[str, Any]) -> dict[str, Any] | None:
    blob = payload.get("area")
    if not isinstance(blob, dict):
        return None
    nested = blob.get("area")
    if "contours" not in blob and isinstance(nested, dict):
        blob = nested
    return blob if isinstance(blob, dict) else None


def geom_from_payload(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    blob = _area_blob(payload)
    if blob is None:
        return None, None
    crs = _clip(blob.get("coordinateSystemCode"), 50)
    contours = blob.get("contours")
    if not isinstance(contours, list):
        return None, crs
    polygons: list[str] = []
    for contour in contours:
        if not isinstance(contour, dict):
            continue
        inners = contour.get("innerContours")
        if not isinstance(inners, list):
            continue
        rings = sorted(
            (item for item in inners if isinstance(item, dict)),
            key=lambda item: (
                item.get("innerContourNumber") is None,
                item.get("innerContourNumber") or 0,
            ),
        )
        ring_wkt: list[str] = []
        for ring in rings:
            points = ring.get("innerContourCoordinates")
            if not isinstance(points, list):
                continue
            wkt = _ring_wkt(points)
            if wkt:
                ring_wkt.append(wkt)
        if ring_wkt:
            polygons.append("(" + ", ".join(ring_wkt) + ")")
    if not polygons:
        return None, crs
    if len(polygons) == 1:
        return "POLYGON" + polygons[0], crs
    return "MULTIPOLYGON(" + ", ".join(polygons) + ")", crs


def row_from_payload(subject: str, fgis_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    geom, crs = geom_from_payload(payload)
    return {
        "subject": _clip(subject, 3),
        "fgis_id": _clip(fgis_id, 50),
        "taxation_piece": _clip(payload.get("originalRegistrationNo"), 10),
        "quarter": _clip(payload.get("forestQuarterRegistrationNo"), 20),
        "area": _area(payload.get("squareNval")),
        "status": _clip(payload.get("statusInd"), 10),
        "actuality_date": _date(payload.get("modifyDttm")),
        "data_kind": KIND_TAXATION_PIECE,
        "geom": geom,
        "crs": crs,
    }


def quarter_row_from_payload(
    subject: str, fgis_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    geom, crs = geom_from_payload(payload)
    row: dict[str, Any] = {
        "subject": _clip(subject, 3),
        "fgis_id": _clip(fgis_id, 50),
        "subforestry": _clip(payload.get("steadRegistrationNo"), 10),
        "quarter": _clip(payload.get("originalRegistrationNo"), 10),
        "tract": (
            _clip(payload.get("tractName"), 150) if "tractName" in payload else None
        ),
        "status": _clip(payload.get("statusInd"), 10),
        "actuality_date": _date(payload.get("modifyDttm")),
        "data_kind": KIND_QUARTERS,
        "geom": geom,
        "crs": crs,
    }
    return row


def ids_from_payload(payload: Any) -> list[str]:
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise TypeError("payload changedOverPeriod должен быть массивом id")
    ids: list[str] = []
    for item in payload:
        if item is None:
            continue
        text = str(item).strip()
        if text:
            ids.append(text[:50])
    return ids
