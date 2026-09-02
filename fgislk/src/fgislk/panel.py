from __future__ import annotations

from fgislk.settings import DATA_KIND, DATA_KIND_LABELS


def panel_manifest() -> dict:
    kind_options = [
        {"value": kind, "label": label}
        for kind, label in DATA_KIND_LABELS.items()
    ]
    return {
        "id": "fgislk",
        "title": "fgislk",
        "status": {
            "path": "/status",
            "rows": "subjects",
            "highlight": {"field": "in_progress", "class": "running"},
            "pagination": {
                "param": "day",
                "prev": "prev_day",
                "next": "next_day",
                "current": "day",
            },
            "filters": [
                {
                    "name": "subject",
                    "type": "text",
                    "optional": True,
                    "label": "Субъект",
                },
                {
                    "name": "data_kind",
                    "type": "select",
                    "optional": True,
                    "label": "Вид реестра",
                    "value": DATA_KIND,
                    "options": kind_options,
                },
            ],
            "columns": [
                {"name": "subject", "label": "Субъект"},
                {"name": "data_kind_label", "label": "Вид реестра"},
                {"name": "period_end", "label": "Дата запроса"},
                {"name": "period_start", "label": "Дата импорта"},
                {"name": "updated_count", "label": "количество данных за период"},
                {"name": "progress", "label": "прогресс"},
                {"name": "error", "label": "Ошибки"},
                {"name": "audit", "label": "Аудит"},
            ],
        },
        "actions": [
            {
                "id": "start",
                "title": "Старт инкремента",
                "method": "GET",
                "path": "/sync",
                "query": {"start": "1"},
                "fields": [
                    {
                        "name": "subject",
                        "type": "text",
                        "optional": True,
                        "label": "Субъект",
                    }
                ],
            },
            {
                "id": "audit",
                "title": "Аудит",
                "method": "GET",
                "path": "/sync",
                "query": {"audit": "1"},
                "fields": [
                    {
                        "name": "subject",
                        "type": "text",
                        "optional": True,
                        "label": "Субъект",
                    },
                    {
                        "name": "day",
                        "type": "date",
                        "optional": True,
                        "label": "С даты",
                    },
                ],
            },
            {
                "id": "stop",
                "title": "Стоп",
                "method": "GET",
                "path": "/sync",
                "query": {"stop": "1"},
                "fields": [],
            },
        ],
        "tables": [],
    }
