# fgislk

## Назначение и границы

Загрузка в общую PostGIS данных ИС ФГИС ЛК (СПД): сейчас только **выделы** в `taxation_piece`. Не UI, не DDL. Кварталы, лесосеки, WFS — позже.

## Требования

- Пишет прикладные таблицы слоёв (**семантика**, без геометрии). Схему не меняет: Alembic не вызывать.
- Идентификация объектов: **субъект** + **учётный номер ФГИС ЛК**.
- Рестарт fgislk не роняет UI (отдельный процесс).
- `/health`: версия + `alembic_revision`. На старте: `GET {MIGRATE_URL}/ready` и `REQUIRED_SCHEMA`; mismatch — не стартовать.
- Ежедневно: к СПД окно `(last_ok + 1) … сегодня` (МСК), без истории — `вчера … сегодня` (`endDate` = сегодня, иначе вчера не входит). В журнал `day` — вчера (закрытый день). Простой сервиса — догон с последней успешной даты, не полный аудит.
- Аудит — `GET /sync?audit=1` с `2023-05-01`; с `day=YYYY-MM-DD` окно с этой даты до сегодня (МСК), `endDate` = сегодня. К СПД сначала весь период; нет `payload` — `start` на месяц вперёд, `endDate` тот же, пока не появится `payload` или `start` позже сегодня. Опционально `subject=`. Инкремент вручную — `GET /sync?start=1` (одно окно, без сужения). Стоп текущего прогона — `GET /sync?stop=1` (без `subject=` и без `day=`; процесс HTTP не гасится). Календарь «3 субъекта в день» не реализуется.
- Параллелизм: не больше `FGIS_MAX_WORKERS` субъектов сразу (по умолчанию 25, потолок 25). Один субъект — один воркер; карточки внутри субъекта последовательно. К СПД — пачки по 1000 GET в одном `curl.exe` (`next`, HTTP/1.1 keep-alive), не новый процесс на каждый id.
- Журнал: `fgis_import_history` (субъект, день-watermark, окно СПД `period_start`…`period_end`, результат, число изменений по СПД за окно, вид данных). Watermark — `MAX(day)` при `result = ok`. `/status`: для текущего прогона `result=running`, `error` пустой (не из последнего журнала), `in_progress`, период окна; после завершения — тот же период в журнале. Аудит пишет `taxation_piece` пачками по 1000 строк; `updated_count` в `/status` растёт после каждой пачки. После пачки в строке выдела — `read_at` (дата чтения, МСК). Повторный аудит (падение процесса, `stop`, новый `audit=1`) не запрашивает карточку, если `read_at >= сегодня − 2 дня`. Инкремент карточки не пропускает.



## Ограничения и допущения

- Импорт ограничен квотами/лимитами ФГИС, не N реплик fgislk без координации.
- Отправка в ФГИС из очереди `exchanges` — процесс канала, не это приложение.
- fgislk карту не публикует; пишет таблицы Spatial data.
- Контур из СПД не пишем: колонка `geom` этим процессом не заполняется и при upsert не трогается. WFS — позже.
- HTTPS к порталу: `FGIS_TLS` в `.env`. Пусто — `schannel` на Windows, `openssl` на Linux. `schannel` — только **Windows** `curl.exe` **(Schannel)**, как НСИ в mirror. OpenSSL в Python и Linux-Docker рвут handshake (`error:0A000410`). `openssl` — системный `curl` (`SECLEVEL=1`) или httpx. Запуск к порталу: `fgislk/run.ps1` на хосте. Сервис Compose `fgislk` — профиль `container`, к порталу не ходит.
- Год лесоустройства не маппим.



## Интерфейсы

- **ИС ФГИС ЛК:** СПД `taxationPiece/changedOverPeriod` и `taxationPiece/{id}`; заголовки `login` / `password` из `.env`. TLS: `FGIS_TLS` (`schannel` / `openssl`).
- **Postgres:** те же `POSTGRES_`*, запись в `taxation_piece` и `fgis_import_history`; не через `api`.
- **migrate:** `/ready` и `REQUIRED_SCHEMA` перед стартом.
- **HTTP:** `/health`, `/ready`, `/status` (`in_progress`, `period_start`/`period_end`, `result=running` пока прогон идёт, `error` не из прошлого журнала). Ручные прогоны (порт `FGISLK_PORT`, по умолчанию 8081):
  - все субъекты: `GET http://127.0.0.1:8081/sync?start=1`, `GET http://127.0.0.1:8081/sync?audit=1`, `GET http://127.0.0.1:8081/sync?audit=1&day=2026-08-30`, `GET http://127.0.0.1:8081/sync?stop=1`;
  - один субъект: `GET http://127.0.0.1:8081/sync?start=1&subject=07`, `GET http://127.0.0.1:8081/sync?audit=1&subject=07`, `GET http://127.0.0.1:8081/sync?audit=1&day=2026-08-30&subject=07` (`stop` с `subject=` нельзя).
- **Потребители:** `api`, `web` (через `api`) — чтение по субъекту и учётному номеру.



## Архитектура решения

ИС ФГИС ЛК → fgislk (`FGIS_TLS`) → `taxation_piece` + `fgis_import_history`. Модель слоя — `[spatialData/CONTEXT.md](../spatialData/CONTEXT.md)`. Цикл после полуночи МСК и на старте; вручную: `start=1` / `audit=1` / `stop=1`. Advisory lock на субъект в Postgres.