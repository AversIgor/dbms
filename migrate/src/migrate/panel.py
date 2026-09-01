from __future__ import annotations


def panel_manifest() -> dict:
    return {
        "id": "migrate",
        "title": "migrate",
        "status": {"path": "/status", "label": "Версия СУБД"},
        "actions": [],
        "tables": [],
    }
