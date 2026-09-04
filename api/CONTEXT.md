# api

## Назначение и границы

Read-only HTTP для внешних ИС: выборки из таблиц Spatial data общей PostGIS. Не импорт СПД, не DDL, не витрина оператора, не XML/PDF/СМЭВ и не карта.

## Требования

- Только чтение. Alembic не вызывать. Схему не менять.
- На старте: `GET {MIGRATE_URL}/ready` и `REQUIRED_SCHEMA`; схема не та — не стартовать.
- `/health`: версия + `alembic_revision`. `/ready` — 503 при mismatch. `/status` и `GET /panel` — для admin; команд импорта нет. В `/panel` — `methods`: `id`, `title`, `method`, `path`, `fields` (как у команд fgislk).
- Геометрию в ответах не отдаём, пока метод явно не потребует контур.
- Нет логина: доступ как у остальных HTTP на хосте.
- JSON-ключи колонок латиницей; даты — ISO `YYYY-MM-DD`. Без фильтра по `subject`, если метод его не принимает. Пустой обязательный query — 400 `{ok: false, error}`.
- Эндпоинты (аналоги 1С). `read_at` = дата обновления в 1С. `history` в карточке — всегда `[]` (регистра истории учётных записей нет).

Связь выдел/лесосека с кварталом (FK нет):

1. `taxation_piece.quarter = quarters.fgis_id` или `clearcut.quarter = quarters.fgis_id` (в СПД в `quarter` чаще лежит учётный номер квартала).
2. иначе `child.quarter = quarters.quarter` и `child.subject = quarters.subject`.

### Методы: запрос и порядок выборки

**`GET /getListQuarters`** (ПолучитьПереченьКварталов). Query: `subforestry`; `tract` нет / пусто / `ВСЕ_УРОЧИЩА` — не фильтровать урочище; `has_clearcuts=1` — только `has_clearcuts = true`. Ответ — массив: `fgis_id`, `quarter`, `tract`, `actuality_date`, `read_at`, `has_clearcuts`, `status`.  
Выборка: одна таблица `quarters`. Фильтр `subforestry` [= `tract`] [AND `has_clearcuts`]. PK и JOIN не нужны.

**`GET /getListTracts`** (ПолучитьПереченьУрочищ). Query: `subforestry`. Ответ — массив объектов `{tract}`.  
Выборка: `quarters`, `WHERE subforestry`, `DISTINCT tract`, `ORDER BY tract`. В `/panel` у `getListQuarters.tract`: `select`, `options` включает `ВСЕ_УРОЧИЩА`, `options_from` — этот метод по полю `subforestry`.

**`GET /getListTractsOfQuarter`** (ПолучитьПереченьУрочищКвартала). Query: `subforestry`, `quarter` (номер без группировки тысяч). Ответ — массив объектов `{tract}`.  
Выборка: `quarters`, `WHERE subforestry AND quarter`, `DISTINCT tract`, `ORDER BY tract`.

**`GET /getQuarterCard`** (КарточкаКвартала). Query: `fgis_id` (повтор или через запятую) — учётные номера кварталов. Ответ `{taxation_pieces, clearcuts, history}`.  
Выборка: (1) `quarters` по PK `fgis_id`; JOIN `taxation_piece` по связи выше; UNION `taxation_piece` напрямую `WHERE quarter IN (fgis_id…)`. (2) то же для `clearcut`. (3) `history` не читается.

**`GET /getQuarterProps`** (РеквизитыКвартала). Query: `fgis_id`. Ответ — объект или `{}`.  
Выборка: `quarters` по PK `fgis_id` (`subject`, `subforestry`, `quarter`, `tract`). JOIN нет.

**`GET /getLocation`** (ПолучитьОписаниеМестоположения). Query: `fgis_id` квартала или выдела.  
Выборка: сначала PK `taxation_piece.fgis_id`; если есть — `taxation_piece` LEFT JOIN `quarters` по связи выше. Иначе PK `quarters.fgis_id`; если есть — `quarters` LEFT JOIN `taxation_piece` по той же связи. Нет ни там ни там — `[]`.

**`GET /getLocationBySubforestryAndQuarter`** (ПолучитьОписаниеМестоположенияПоЛесничествамИКварталам). Query: `subforestry`, `quarter`.  
Выборка: только `quarters`, `WHERE subforestry AND quarter`, `ORDER BY actuality_date DESC`. JOIN нет.

**`GET /getQuarterFgisId`** (ПолучитьУчетныйНомерКвартала). Query: `subforestry`, `quarter`; `tract` пусто — пустое урочище. Ответ — строка `fgis_id` или `""`.  
Выборка: `quarters`, `WHERE subforestry AND quarter AND COALESCE(tract,'') LIKE tract`, `ORDER BY actuality_date DESC LIMIT 1`. В `/panel` у `tract`: `select`, `options_from` — `getListTracts` по полю `subforestry`.

**`GET /getTaxationPieceFgisId`** (ПолучитьУчетныйНомерВыдела). Query: `quarter_fgis_id`, `taxation_piece`.  
Выборка: `quarters` по PK `fgis_id = quarter_fgis_id`, JOIN `taxation_piece` по связи выше и `taxation_piece = номер`, `ORDER BY read_at, actuality_date DESC LIMIT 1`. Пусто — `taxation_piece` напрямую `WHERE quarter = quarter_fgis_id AND taxation_piece = номер`.

**`GET /getClearcutFgisId`** (ПолучитьУчетныйНомерЛесосеки). Query: `quarter_fgis_id`, `clearcut_no`, `area`.  
Выборка: как у выдела, но `clearcut`: JOIN по связи с кварталом и `clearcut_no` + `area`; иначе `clearcut.quarter = quarter_fgis_id` и те же номер/площадь. `LIMIT 1`.

**`GET /getListClearcuts`** (ПолучитьПереченьЛесосек). Query: `quarter_fgis_id`.  
Выборка: `quarters` по PK, JOIN `clearcut` по связи; пусто — `clearcut WHERE quarter = quarter_fgis_id`.

**`GET /getClearcutProps`** (РеквизитыЛесосеки). Query: `fgis_id` лесосеки.  
Выборка: `clearcut` по PK `fgis_id`; LEFT JOIN LATERAL одна строка `quarters` по связи (предпочтение `quarters.fgis_id = clearcut.quarter`).

## Ограничения и допущения

- Один процесс выдачи; не N реплик «на вырост».
- Методы 1С — отдельные эндпоинты в том же роутере, без пустых заглушек.
- Индексы под эти WHERE/JOIN — в migrate (`ix_quarters_subforestry_quarter`, `ix_taxation_piece_quarter_piece`, `ix_clearcut_quarter_no_area`).

## Интерфейсы

- **Postgres:** те же `POSTGRES_*`; только `SELECT`.
- **migrate:** `/ready` и `REQUIRED_SCHEMA` перед стартом.
- **HTTP** (порт `API_PORT`, по умолчанию 8083): `/health`, `/ready`, `/status`, `GET /panel`, методы выше.
- **admin:** `/panel`, `/status`; вызов `methods` через прокси. `API_URL`.
- **Внешние ИС:** HTTP этого раздела; ключ связи — учётный номер ФГИС ЛК (`fgis_id`).

## Архитектура решения

Внешняя ИС → `GET` метода → `SELECT` из `quarters` / `taxation_piece` / `clearcut`. Методы — модуль-роутер. Модель слоя — [spatialData/CONTEXT.md](../spatialData/CONTEXT.md).
