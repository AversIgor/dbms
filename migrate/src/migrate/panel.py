from __future__ import annotations

from migrate.rows import tables_catalog


def panel_manifest() -> dict:
    return {
        "id": "migrate",
        "title": "migrate",
        "status": {"path": "/status", "label": "Версия СУБД"},
        "actions": [],
        "tables": [
            {
                "id": "rows",
                "title": "Таблицы БД",
                "kind": "browser",
                "path": "/rows",
                "open_label": "Открыть",
                "table_param": "table",
                "table_label": "Таблица",
                "tables": tables_catalog(),
                "search_field_param": "field",
                "search_value_param": "q",
                "page_param": "page",
                "size_param": "size",
                "delete": {"path": "/rows/delete", "method": "POST"},
            }
        ],
    }
