# api

## Назначение и границы

Read-only HTTP для внешних ИС: выборки из таблиц Spatial data общей PostGIS. Не импорт СПД, не DDL, не витрина оператора, не XML/PDF/СМЭВ и не карта.

## Требования

- Только чтение. Alembic не вызывать. Схему не менять.
- На старте: `GET {MIGRATE_URL}/ready` и `REQUIRED_SCHEMA`; схема не та — не стартовать.
- `/health`: версия + `alembic_revision`. `/ready` — 503 при mismatch. `/status` и `GET /panel` — для admin; команд импорта нет. В `/panel` — `methods`: `id`, `title`, `method`, `path`, `fields` (как у команд fgislk).
- Геометрию в ответах не отдаём, пока метод явно не потребует контур.
- Нет логина: доступ как у остальных HTTP на хосте.
- `GET /getListQuarters`: перечень кварталов по участковому лесничеству (аналог 1С `ПолучитьПереченьКварталов`). Query: `subforestry` обязателен; `tract` нет / пусто / `ВСЕ_УРОЧИЩА` — все урочища; `has_clearcuts=1` — только `has_clearcuts = true`, иначе фильтр не ставим. Без фильтра по `subject`. JSON-массив, ключи колонок: `fgis_id`, `quarter`, `tract`, `actuality_date`, `read_at` (в 1С — дата обновления), `has_clearcuts`, `status`. Даты — ISO `YYYY-MM-DD`.

## Ограничения и допущения

- Один процесс выдачи; не N реплик «на вырост».
- Остальные ~14 методов 1С — отдельные эндпоинты в том же роутере, без пустых заглушек.
- Индекс по `subforestry` в migrate не заводим, пока не понадобится.

## Интерфейсы

- **Postgres:** те же `POSTGRES_*`; только `SELECT`.
- **migrate:** `/ready` и `REQUIRED_SCHEMA` перед стартом.
- **HTTP** (порт `API_PORT`, по умолчанию 8083): `/health`, `/ready`, `/status`, `GET /panel`, `GET /getListQuarters`.
- **admin:** `/panel`, `/status`; вызов `methods` через прокси. `API_URL`.
- **Внешние ИС:** HTTP этого раздела; ключ связи — учётный номер ФГИС ЛК (`fgis_id`).

## Архитектура решения

Внешняя ИС → `GET /getListQuarters` → `SELECT` из `quarters`. Методы — модуль-роутер. Модель слоя — [spatialData/CONTEXT.md](../spatialData/CONTEXT.md).
