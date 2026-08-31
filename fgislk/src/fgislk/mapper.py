from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from fgislk.settings import DATA_KIND


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


def row_from_payload(subject: str, fgis_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "subject": _clip(subject, 3),
        "fgis_id": _clip(fgis_id, 50),
        "taxation_piece": _clip(payload.get("originalRegistrationNo"), 10),
        "quarter": _clip(payload.get("forestQuarterRegistrationNo"), 20),
        "area": _area(payload.get("squareNval")),
        "status": _clip(payload.get("statusInd"), 10),
        "data_kind": DATA_KIND,
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
