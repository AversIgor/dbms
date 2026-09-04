# constants

## Назначение и границы

Типизированные прикладные настройки программы: таблица `constant` в общей PostGIS и HTTP чтения/записи. Единственный процесс, который ходит в эту таблицу. Не DDL, не импорт СПД, не выдача внешним ИС, не витрина оператора.

## Требования

- Виды значений: `string`, `number`, `date` (`YYYY-MM-DD`), `boolean`. Канон в БД — текст; в JSON — нативный тип kind.
- Ключи не создавать и не удалять через HTTP; менять только `value` при неизменном `kind`.
- На старте: `GET {MIGRATE_URL}/ready` и `REQUIRED_SCHEMA`; схема не та — не стартовать.
- `/health`: версия + `alembic_revision`. Alembic не вызывать.
- Потребители читают `GET /items/{key}`, admin — список и `PUT`. Фоллбека на `.env` в этом разделе нет (кроме `POSTGRES_*`, порта и `MIGRATE_URL`).

## Ограничения и допущения

- Один процесс; не кэш «на вырост».
- Новые ключи — миграция `migrate`, не API.
- Пул SQLAlchemy потребителей с размера на старте не пересобирается.

## Интерфейсы

- **Postgres:** те же `POSTGRES_*`; только таблица `constant`.
- **migrate:** `/ready` и `REQUIRED_SCHEMA` перед стартом. Сид строк — миграция.
- **HTTP** (порт `CONSTANTS_PORT`, по умолчанию 8084): `/health`, `/ready`, `/status`, `GET /panel`, `GET /items`, `GET /items/{key}`, `PUT /items/{key}` JSON `{value}`.
- **admin:** карточка «Константы», прокси, `tables.kind = kv`.
- **fgislk и прочие:** `CONSTANTS_URL`, не `SELECT` в `constant`.

## Архитектура решения

migrate (`upgrade`, сид из env) → таблица `constant` → этот процесс (разбор типов) → HTTP. Потребители и admin не читают `.env` для ключей таблицы.
