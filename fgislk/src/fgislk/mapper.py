from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fgislk.settings import KIND_CLEARCUT, KIND_QUARTERS, KIND_TAXATION_PIECE
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
    """Даты СПД (modifyDttm, limitationDt): ISO, epoch с/мс, /Date(ms)/."""
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


def _point_xy(point: Any) -> tuple[str, str] | None:
    if isinstance(point, dict):
        x = _coord(point.get("longitude"))
        y = _coord(point.get("latitude"))
    elif isinstance(point, (list, tuple)) and len(point) >= 2:
        x = _coord(point[0])
        y = _coord(point[1])
    else:
        return None
    if x is None or y is None:
        return None
    return x, y


def _ring_wkt(points: list[Any]) -> str | None:
    dicts = [p for p in points if isinstance(p, dict)]
    if dicts:
        ordered = sorted(
            dicts,
            key=lambda p: (p.get("pointNumber") is None, p.get("pointNumber") or 0),
        )
    else:
        ordered = points
    coords: list[str] = []
    for point in ordered:
        xy = _point_xy(point)
        if xy is None:
            continue
        coords.append(f"{xy[0]} {xy[1]}")
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


def _polygon_from_rings(rings: list[Any]) -> str | None:
    ring_wkt: list[str] = []
    for ring in rings:
        if not isinstance(ring, list):
            continue
        wkt = _ring_wkt(ring)
        if wkt:
            ring_wkt.append(wkt)
    if not ring_wkt:
        return None
    return "(" + ", ".join(ring_wkt) + ")"


def _wkt_from_geojson(geom: dict[str, Any]) -> str | None:
    gtype = geom.get("type")
    coordinates = geom.get("coordinates")
    if not isinstance(coordinates, list):
        return None
    if gtype == "Polygon":
        poly = _polygon_from_rings(coordinates)
        return ("POLYGON" + poly) if poly else None
    if gtype == "MultiPolygon":
        polys: list[str] = []
        for item in coordinates:
            if not isinstance(item, list):
                continue
            poly = _polygon_from_rings(item)
            if poly:
                polys.append(poly)
        if not polys:
            return None
        if len(polys) == 1:
            return "POLYGON" + polys[0]
        return "MULTIPOLYGON(" + ", ".join(polys) + ")"
    return None


def _geom_from_clearcut_location(
    loc: Any,
) -> tuple[str | None, str | None]:
    if not isinstance(loc, dict):
        return None, None
    features = loc.get("features")
    if not isinstance(features, list):
        return None, None
    crs: str | None = None
    parts: list[str] = []
    for feat in features:
        if not isinstance(feat, dict):
            continue
        props = feat.get("properties")
        if crs is None and isinstance(props, dict):
            crs = _clip(
                props.get("srid_nsi") or props.get("coordinateSystemCode"), 50
            )
        geometry = feat.get("geometry")
        if not isinstance(geometry, dict):
            continue
        wkt = _wkt_from_geojson(geometry)
        if wkt:
            parts.append(wkt)
    if not parts:
        return None, crs
    if len(parts) == 1:
        return parts[0], crs
    unpacked: list[str] = []
    for wkt in parts:
        if wkt.startswith("POLYGON"):
            unpacked.append(wkt[len("POLYGON") :])
        elif wkt.startswith("MULTIPOLYGON(") and wkt.endswith(")"):
            unpacked.append(wkt[len("MULTIPOLYGON(") : -1])
    if not unpacked:
        return parts[0], crs
    return "MULTIPOLYGON(" + ", ".join(unpacked) + ")", crs


def geom_from_payload(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    blob = _area_blob(payload)
    if blob is not None:
        crs = _clip(blob.get("coordinateSystemCode"), 50)
        contours = blob.get("contours")
        if isinstance(contours, list):
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
            if polygons:
                if len(polygons) == 1:
                    return "POLYGON" + polygons[0], crs
                return "MULTIPOLYGON(" + ", ".join(polygons) + ")", crs
        if crs is not None:
            return None, crs
    return _geom_from_clearcut_location(payload.get("clearcutLocation"))


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


def clearcut_row_from_payload(
    subject: str, fgis_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    geom, crs = geom_from_payload(payload)
    return {
        "subject": _clip(subject, 3),
        "fgis_id": _clip(fgis_id, 50),
        "quarter": _clip(payload.get("quarterNo"), 20),
        "area": _area(payload.get("squareNval")),
        "status": _clip(payload.get("status"), 10),
        "actuality_date": _date(payload.get("modifyDttm")),
        "limitation_dt": _date(payload.get("limitationDt")),
        "clearcut_no": _clip(payload.get("clearcutInDocNo"), 50),
        "basis_doc_no": _clip(payload.get("basisDocNo"), 50),
        "data_kind": KIND_CLEARCUT,
        "geom": geom,
        "crs": crs,
    }


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


def ids_from_clearcut_list(payload: Any) -> list[str]:
    raw: Any = payload
    if isinstance(payload, dict):
        if "clearcutNo" in payload:
            raw = payload.get("clearcutNo")
        else:
            raw = payload.get("payload", payload)
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raise TypeError("get-no-by-quarter: ожидался массив id")
    ids: list[str] = []
    for item in raw:
        if item is None:
            continue
        if isinstance(item, dict):
            text = None
            for key in (
                "registrationNo",
                "clearcutRegistrationNo",
                "clearcutNo",
                "id",
                "fgisId",
            ):
                text = _clip(item.get(key), 50)
                if text:
                    break
            if text:
                ids.append(text)
            continue
        text = str(item).strip()
        if text:
            ids.append(text[:50])
    return ids
