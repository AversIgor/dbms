from __future__ import annotations


def panel_manifest() -> dict:
    return {
        "id": "api",
        "title": "api",
        "status": {"path": "/status", "label": "API"},
        "actions": [],
        "tables": [],
        "methods": [
            {
                "id": "getListQuarters",
                "title": "Перечень кварталов",
                "method": "GET",
                "path": "/getListQuarters",
                "fields": [
                    {
                        "name": "subforestry",
                        "type": "text",
                        "label": "Участковое лесничество",
                    },
                    {
                        "name": "tract",
                        "type": "text",
                        "optional": True,
                        "label": "Урочище",
                        "value": "ВСЕ_УРОЧИЩА",
                    },
                    {
                        "name": "has_clearcuts",
                        "type": "checkbox",
                        "optional": True,
                        "label": "Только с лесосеками",
                    },
                ],
            },
        ],
    }
