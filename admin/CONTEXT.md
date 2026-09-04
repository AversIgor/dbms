# admin

## Назначение и границы

Тонкая HTML-витрина для оператора: карточки разделов, статусы, кнопки команд, таблицы из манифеста раздела. Не источник правды: не ходит в PostGIS, не вызывает Alembic, не знает правил импорта СПД. Логика и данные — HTTP разделов (`GET /panel` и дальше).

Не прикладной UI, не карта, не формы НСИ.

## Требования

- Одна страница: блок на каждый раздел из каталога. `spatialData` без своего HTTP — не выдуманный API; `title` в каталоге — «Пространственные данные». Таблицы — из `GET /panel` раздела `tables_from` (`migrate`), прокси `/p/migrate/…`.
- Каталог зашит: `migrate`, `constants`, `fgislk`, `api`, `spatialData`. Базовый URL — из env (`MIGRATE_URL`, `CONSTANTS_URL`, `FGISLK_URL`, `API_URL`); у spatialData — stub, без URL, поле `tables_from`. `GET /catalog` отдаёт `id`, `title`, `has_http`, при необходимости `stub` и `tables_from`; `base_url` в браузер не отдавать.
- Команды, колонки, фильтры и пагинация — только из `GET /panel` раздела, не зашивать `start=1` в HTML. Нет отдельного блока «Служебные данные».
- Браузер ходит только на admin. Прокси `/p/{id}/…` — только на URL из каталога. Отказ: пустой путь, начинается с `/`, `\`, сегменты `.` или `..`, схема не `http`/`https`, чужой hostname или port, userinfo. Методы: `GET`/`PUT`/`POST`/`PATCH`/`HEAD`. Наверх — только заголовок `content-type`.
- Карточка HTTP-раздела: `GET /p/{id}/panel`, затем `actions` / `status` / `tables` / `methods`. Checkbox в команде всегда кладёт в query `1` или `0`. У команды рядом с кнопкой — HTTP-статус и поле `error` из JSON ответа. Статус опрашивать каждые 5 с. Нет `status.columns` — фолбэк по JSON `/status`: массив `subjects`, иначе `revision` (префикс до `_`), иначе `history`, иначе `pre` с JSON.
- `methods`: строка `method` + `path` + поля из манифеста и кнопка вызова. Ответ — модальное окно (массив объектов — таблица, иначе JSON). Пути методов в HTML не зашивать. У `select` с `options_from`: догрузить options из другого `methods[].id` того же panel (`path`/`query` из манифеста, не из HTML); ключ значения — `options_from.value`; статичные `options` оставить первыми.
- `tables.kind = browser`: выбор таблицы, поиск по полю, пагинация — параметры из манифеста и ответ `/rows`. `embed` — сразу на карточке (без кнопки «Открыть»); иначе кнопка открывает окно. Таблица с `host` — только в карточке этого раздела. Удаление — `POST` JSON на `delete.path` (выбранные `ids` или `all_matching`; без поиска — вся таблица после confirm). `all_matching` — тот же запрос, пока в ответе `done` не true; рядом — сколько уже удалено. Не зашивать имена таблиц БД в HTML.
- `tables.kind = kv`: список ключ/тип/значение из `path`, сохранение `PUT` JSON `{value}` на `save.path/{key}`; поле ввода по `kind` (`string`/`number`/`date`/`boolean`). Ключи в HTML не зашивать.
- `POSTGRES_*` не показывать. Логина нет: доступ как у ручных GET на хосте.
- Не оркестратор: не рестартует процессы, не делает `upgrade`.

## Ограничения и допущения

- Стек: FastAPI, один HTML + vanilla JS. Нет React/Vite/MapLibre.
- `FGISLK_URL` часто указывает на хост (`run.ps1`), не на сервис Compose `fgislk`.
- Прокси: таймаут 20 с, редиректы не следуем.

## Интерфейсы

- **HTTP:** порт `ADMIN_PORT` (по умолчанию 8082). `/` — страница; `/health`; `/catalog` (без URL бэкендов); `/p/{id}/{path}` — прокси, `MIGRATE_URL`/`CONSTANTS_URL`/`FGISLK_URL`/`API_URL` в браузер не светит.
- **migrate / constants / fgislk / api:** `MIGRATE_URL`, `CONSTANTS_URL`, `FGISLK_URL`, `API_URL`. Стык — JSON `/panel`, `/status`, команды, `methods` и таблицы из манифеста.
- **Postgres:** нет.

## Архитектура решения

Каталог → fetch `/panel` через прокси → рендер кнопок/таблиц/`methods` → те же HTTP раздела. Нет своей БД и нет прикладных правил.
