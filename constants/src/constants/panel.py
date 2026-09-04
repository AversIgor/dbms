from __future__ import annotations


def panel_manifest() -> dict:
    return {
        "id": "constants",
        "title": "Константы",
        "status": {"path": "/status", "label": "Константы"},
        "actions": [],
        "tables": [
            {
                "id": "items",
                "title": "Константы",
                "kind": "kv",
                "embed": True,
                "path": "/items",
                "save": {"path": "/items", "method": "PUT"},
            }
        ],
        "methods": [],
    }
