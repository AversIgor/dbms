from __future__ import annotations

from admin.settings import api_url, constants_url, fgislk_url, migrate_url

SPATIAL_STUB = (
    "Нет HTTP-процесса; данные в PostGIS через migrate и fgislk."
)


def catalog() -> list[dict]:
    return [
        {
            "id": "migrate",
            "title": "migrate",
            "base_url": migrate_url(),
        },
        {
            "id": "constants",
            "title": "Константы",
            "base_url": constants_url(),
        },
        {
            "id": "fgislk",
            "title": "fgislk",
            "base_url": fgislk_url(),
        },
        {
            "id": "api",
            "title": "api",
            "base_url": api_url(),
        },
        {
            "id": "spatialData",
            "title": "Пространственные данные",
            "base_url": None,
            "stub": SPATIAL_STUB,
            "tables_from": "migrate",
        },
    ]


def public_catalog() -> list[dict]:
    items = []
    for section in catalog():
        item = {
            "id": section["id"],
            "title": section["title"],
            "has_http": bool(section.get("base_url")),
        }
        if section.get("stub"):
            item["stub"] = section["stub"]
        if section.get("tables_from"):
            item["tables_from"] = section["tables_from"]
        items.append(item)
    return items


def section_by_id(section_id: str) -> dict | None:
    for section in catalog():
        if section["id"] == section_id:
            return section
    return None
