# migrate

## Назначение и границы

Единственный владелец DDL общей PostGIS. Выкладка схемы (`upgrade head`), проверка готовности для остальных процессов. Не отдаёт НСИ и карту. Insert/update прикладных строк нет, кроме сида таблицы `constant` при миграции. Просмотр и удаление строк канонических таблиц (не `constant`) — HTTP для admin.

Актуальная структура БД для людей: [`schema.md`](schema.md).

## Требования

- Схема меняется только здесь. `constants`, `fgislk` и `api` Alembic не вызывают.
- Смена структуры (`models.py`, `alembic/versions/`, расширения) в том же изменении обновляет [`schema.md`](schema.md).
- Compose: `db` healthy → этот процесс (`serve --upgrade`) → потребители. `upgrade head`, затем HTTP.
- Одна реплика; параллельный `upgrade` запрещён.
- Нет API «создай колонку». Кнопки upgrade в браузере нет.
- `GET /rows`: таблицы из `models.py` кроме `constant` (не `alembic_version`, не PostGIS). Список с пагинацией и поиском по выбранному полю; `geom` не отдавать. `POST /rows/delete`: выбранные PK или все найденные (`all_matching`; пустой поиск — вся таблица). Лимита на число найденных нет.

## Ограничения и допущения

- Канон таблиц: `src/migrate/models.py`. Seed не в миграциях, кроме `constant`: при `upgrade` строки и значения из env (пусто — дефолты кода).
- `downgrade` — не автодеплой.
- На старте один пользователь Postgres (позже можно развести DDL/DML).
- Код других разделов не читать, пока задача не про стык с ними.
- Удаление не каскадит в другие таблицы (FK между слоями нет).

## Интерфейсы

- **Postgres:** `POSTGRES_*` из `.env` (права DDL). Другие процессы не ходят сюда за DDL.
- **HTTP:** `/health` (жив), `/ready` (БД есть и `revision == head`, иначе 503), `/status`, `GET /panel` (манифест для admin, без action upgrade), `GET /settings` (`writable: false`). `GET /rows?table=&field=&q=&page=&size=` — строки (не `constant`). `POST /rows/delete` JSON `{table, ids}` или `{table, all_matching: true}` (опционально `field`, `q`; без `q` — вся таблица). Нет HTML-страницы схемы.
- **admin:** чтение `/panel`, `/status`, `/rows`; удаление через `/rows/delete`. Таблицы из манифеста — в карточке Spatial data, не в migrate. Константы — HTTP раздела `constants`. upgrade из UI нет.
- **Потребители:** `GET {MIGRATE_URL}/ready` + свой `REQUIRED_SCHEMA`; несовпадение revision — не стартовать.

## Архитектура решения

Новая таблица: нужда в потребителе → `models.py` → `revision --autogenerate` → проверить SQL → выкладка migrate первым → затем потребитель. Ломающий дроп: сначала код без колонки, потом миграция. Реестр `/rows` — те же mapper’ы `Base`. `upgrade`: пустая БД — `0001_initial`; уже есть таблицы или `alembic_version` не из текущих scripts — stamp head, без CREATE.

CLI: `upgrade` | `current` | `history` | `revision -m` (разработчик) | `serve` | `downgrade`.
