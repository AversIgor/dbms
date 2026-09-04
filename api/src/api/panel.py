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
                        "type": "select",
                        "optional": True,
                        "label": "Урочище",
                        "value": "ВСЕ_УРОЧИЩА",
                        "options": ["ВСЕ_УРОЧИЩА"],
                        "options_from": {
                            "method": "getListTracts",
                            "query": {"subforestry": "subforestry"},
                            "value": "tract",
                        },
                    },
                    {
                        "name": "has_clearcuts",
                        "type": "checkbox",
                        "optional": True,
                        "label": "Только с лесосеками",
                    },
                ],
            },
            {
                "id": "getListTracts",
                "title": "Перечень урочищ",
                "method": "GET",
                "path": "/getListTracts",
                "fields": [
                    {
                        "name": "subforestry",
                        "type": "text",
                        "label": "Участковое лесничество",
                    },
                ],
            },
            {
                "id": "getListTractsOfQuarter",
                "title": "Урочища квартала",
                "method": "GET",
                "path": "/getListTractsOfQuarter",
                "fields": [
                    {
                        "name": "subforestry",
                        "type": "text",
                        "label": "Участковое лесничество",
                    },
                    {"name": "quarter", "type": "text", "label": "Номер квартала"},
                ],
            },
            {
                "id": "getQuarterCard",
                "title": "Карточка квартала",
                "method": "GET",
                "path": "/getQuarterCard",
                "fields": [
                    {
                        "name": "fgis_id",
                        "type": "text",
                        "label": "Учётный номер квартала (через запятую)",
                    },
                ],
            },
            {
                "id": "getQuarterProps",
                "title": "Реквизиты квартала",
                "method": "GET",
                "path": "/getQuarterProps",
                "fields": [
                    {
                        "name": "fgis_id",
                        "type": "text",
                        "label": "Учётный номер квартала",
                    },
                ],
            },
            {
                "id": "getLocation",
                "title": "Описание местоположения",
                "method": "GET",
                "path": "/getLocation",
                "fields": [
                    {
                        "name": "fgis_id",
                        "type": "text",
                        "label": "Учётный номер квартала или выдела",
                    },
                ],
            },
            {
                "id": "getLocationBySubforestryAndQuarter",
                "title": "Местоположение по лесничеству и кварталу",
                "method": "GET",
                "path": "/getLocationBySubforestryAndQuarter",
                "fields": [
                    {
                        "name": "subforestry",
                        "type": "text",
                        "label": "Участковое лесничество",
                    },
                    {"name": "quarter", "type": "text", "label": "Номер квартала"},
                ],
            },
            {
                "id": "getQuarterFgisId",
                "title": "Учётный номер квартала",
                "method": "GET",
                "path": "/getQuarterFgisId",
                "fields": [
                    {
                        "name": "subforestry",
                        "type": "text",
                        "label": "Участковое лесничество",
                    },
                    {
                        "name": "tract",
                        "type": "select",
                        "optional": True,
                        "label": "Урочище",
                        "options": [""],
                        "options_from": {
                            "method": "getListTracts",
                            "query": {"subforestry": "subforestry"},
                            "value": "tract",
                        },
                    },
                    {"name": "quarter", "type": "text", "label": "Номер квартала"},
                ],
            },
            {
                "id": "getTaxationPieceFgisId",
                "title": "Учётный номер выдела",
                "method": "GET",
                "path": "/getTaxationPieceFgisId",
                "fields": [
                    {
                        "name": "quarter_fgis_id",
                        "type": "text",
                        "label": "Учётный номер квартала",
                    },
                    {
                        "name": "taxation_piece",
                        "type": "text",
                        "label": "Номер выдела",
                    },
                ],
            },
            {
                "id": "getClearcutFgisId",
                "title": "Учётный номер лесосеки",
                "method": "GET",
                "path": "/getClearcutFgisId",
                "fields": [
                    {
                        "name": "quarter_fgis_id",
                        "type": "text",
                        "label": "Учётный номер квартала",
                    },
                    {
                        "name": "clearcut_no",
                        "type": "text",
                        "label": "Номер лесосеки",
                    },
                    {"name": "area", "type": "text", "label": "Площадь"},
                ],
            },
            {
                "id": "getListClearcuts",
                "title": "Перечень лесосек",
                "method": "GET",
                "path": "/getListClearcuts",
                "fields": [
                    {
                        "name": "quarter_fgis_id",
                        "type": "text",
                        "label": "Учётный номер квартала",
                    },
                ],
            },
            {
                "id": "getClearcutProps",
                "title": "Реквизиты лесосеки",
                "method": "GET",
                "path": "/getClearcutProps",
                "fields": [
                    {
                        "name": "fgis_id",
                        "type": "text",
                        "label": "Учётный номер лесосеки",
                    },
                ],
            },
        ],
    }
