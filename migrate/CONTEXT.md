# migrate

## Назначение и границы

Единственный владелец DDL общей PostGIS. Выкладка схемы (`upgrade head`), проверка готовности для остальных процессов. Не отдаёт НСИ и карту. Insert/update прикладных строк нет. Просмотр и удаление строк канонических таблиц — HTTP для admin.

Актуальная структура БД для людей: [`schema.md`](schema.md).

## Требования

- Схема меняется только здесь. `fgislk` Alembic не вызывает.
- Смена структуры (`models.py`, `alembic/versions/`, расширения) в том же изменении обновляет [`schema.md`](schema.md).
- Compose: `db` healthy → этот процесс (`serve --upgrade`) → потребители. `upgrade head`, затем HTTP.
- Одна реплика; параллельный `upgrade` запрещён.
- Нет API «создай колонку». Кнопки upgrade в браузере нет.
- `GET /rows`: только таблицы из `models.py` (не `alembic_version`, не PostGIS). Список с пагинацией и поиском по выбранному полю; `geom` не отдавать. `POST /rows/delete`: выбранные PK или все найденные при непустом поиске.

## Ограничения и допущения

- Канон таблиц: `src/migrate/models.py`. Seed не в миграциях.
- `downgrade` — не автодеплой.
- На старте один пользователь Postgres (позже можно развести DDL/DML).
- Код других разделов не читать, пока задача не про стык с ними.
- Удаление не каскадит в другие таблицы (FK между слоями нет).

## Интерфейсы

- **Postgres:** `POSTGRES_*` из `.env` (права DDL). Другие процессы не ходят сюда за DDL.
- **HTTP:** `/health` (жив), `/ready` (БД есть и `revision == head`, иначе 503), `/status`, `GET /panel` (манифест для admin, без action upgrade), `GET /settings` (`writable: false`). `GET /rows?table=&field=&q=&page=&size=` — строки. `POST /rows/delete` JSON `{table, ids}` или `{table, field, q, all_matching: true}`. Нет HTML-страницы схемы.
- **admin:** чтение `/panel`, `/status`, `/rows`; удаление через `/rows/delete`. upgrade из UI нет.
- **Потребители:** `GET {MIGRATE_URL}/ready` + свой `REQUIRED_SCHEMA`; несовпадение revision — не стартовать.

## Архитектура решения

Новая таблица: нужда в потребителе → `models.py` → `revision --autogenerate` → проверить SQL → выкладка migrate первым → затем потребитель. Ломающий дроп: сначала код без колонки, потом миграция. Реестр `/rows` — те же mapper’ы `Base`.

CLI: `upgrade` | `current` | `history` | `revision -m` (разработчик) | `serve` | `downgrade`.
