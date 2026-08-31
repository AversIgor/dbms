# Схема БД (актуальная)

Источник: `alembic/versions/` + `src/migrate/models.py`. Head: `0005_taxation_piece_read_at`.

```mermaid
erDiagram
  alembic_version {
    varchar version_num PK
  }
  taxation_piece {
    varchar subject PK "субъект, индекс"
    varchar fgis_id PK "учётный номер выдела ФГИС ЛК, индекс"
    varchar taxation_piece "номер выдела"
    varchar quarter "номер квартала"
    numeric area "площадь"
    varchar status "status"
    date read_at "дата чтения из СПД, индекс с субъектом"
    geometry geom "контур, gist"
  }
  fgis_import_history {
    int id PK
    varchar subject "субъект"
    date day "последний день закрытого окна"
    date period_start "начало окна СПД"
    date period_end "конец окна СПД"
    varchar result "ok / error"
    int updated_count "сколько строк upsert"
    varchar data_kind "вид данных"
    text error "текст ошибки"
    timestamptz ran_at "когда записали"
  }
```

| Объект | Назначение |
| --- | --- |
| extension `postgis` | геометрия (миграция `0001_postgis`) |
| `alembic_version` | текущая revision |
| `taxation_piece` | выдел: семантика + контур (`0002`) + `read_at` (`0005_taxation_piece_read_at`) |
| `fgis_import_history` | журнал прогонов fgislk (`0003` + окно `0004_fgis_import_period`) |
| таблицы PostGIS (`spatial_ref_sys` и др.) | ставит расширение, не описывать в `models.py` |

Связь с другими разделами — пара `subject` + `fgis_id` (см. [`spatialData/CONTEXT.md`](../spatialData/CONTEXT.md)). Watermark ежедневного импорта — `MAX(day)` успешных строк `fgis_import_history` по субъекту и `data_kind`. Аудит не ходит в СПД за карточкой, если `read_at` не старше 2 дней (МСК).
