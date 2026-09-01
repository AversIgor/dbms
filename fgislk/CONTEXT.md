# fgislk

## Назначение и границы

Загрузка в общую PostGIS данных ИС ФГИС ЛК (СПД): сейчас только **выделы** в `taxation_piece`. Не прикладной UI, не DDL. Кварталы, лесосеки, WFS — позже.

## Требования

- Пишет прикладные таблицы слоёв (**семантика**, без геометрии). Схему не меняет: Alembic не вызывать. Нет поля в карточке — не затираем уже записанную дату.
- Идентификация объектов: **субъект** + **учётный номер ФГИС ЛК**.
- Рестарт fgislk не гасит migrate (отдельный процесс).
- `/health`: версия + `alembic_revision`. На старте: `GET {MIGRATE_URL}/ready` и `REQUIRED_SCHEMA`; mismatch — не стартовать.
- Ежедневно: к СПД окно `(last_ok + 1) … сегодня` (МСК), без истории — `вчера … сегодня` (`endDate` = сегодня, иначе вчера не входит). В журнал `day` — вчера (закрытый день). Простой сервиса — догон непрокачанных дней, не полный аудит. `start=1` всегда запускает этот догон. Успешный аудит (`period_start` = 2023-05-01) не закрывает инкремент своего `day`: watermark = `day − 1`. `ok` без окна СПД день не закрывает. Последняя строка журнала `error` — повторить этот `day`, даже если раньше был `ok`.
- Аудит — `GET /sync?audit=1` с `2023-05-01`; с `day=YYYY-MM-DD` окно с этой даты до сегодня (МСК), `endDate` = сегодня. К СПД сначала весь период; нет `payload` — `start` на месяц вперёд, `endDate` тот же, пока не появится `payload` или `start` позже сегодня. Опционально `subject=`. 
- Запуск процесса вручную — `GET /sync?start=1` (`audit=0 - ежедневный сценарий`). 
- Стоп всех текущих процессов— `GET /sync?stop=1.`Работа всех процессов раздела останавливается.
- Параллелизм: не больше `FGIS_MAX_WORKERS` субъектов сразу (по умолчанию 25, потолок 25). Один субъект — один воркер; карточки внутри субъекта последовательно. К СПД — пачки по 1000 GET в одном `curl.exe` (`next`, HTTP/1.1 keep-alive), не новый процесс на каждый id.
- Журнал: `fgis_import_history` (субъект, день-watermark, окно СПД `period_start`…`period_end`, результат, число обновлённых карточек, вид данных). Watermark инкремента — `MAX(day)` при `result = ok` и окне не-аудита; для аудита с `period_start` = 2023-05-01 это `day − 1`; `ok` без `period_start` день не закрывает; после `error` — повтор дня ошибки. Аудит в журнал пишет пачки по 1000 (`result=partial`, watermark не закрывает); финал — `ok`. Инкремент пишет и `ok` с `updated_count=0`, если за окно не было изменений. `/status`: срез по **дате запроса** `period_end` (`day=` в query, МСК, по умолчанию сегодня) — **одна строка на субъект** с максимальным `updated_count`; `prev_day` / `next_day`. Отбор `subject=`, `data_kind=` (сейчас `taxation_piece` — выделы). Живые воркеры — если `period_end` совпадает со срезом, вместо журнала, `result=running`, `progress` = доля `updated_count`/`changed_total`. Прошлая строка — в `last`. Признак аудита без колонки БД: `period_start` = 2023-05-01 или живой `mode=audit`. Аудит пишет `taxation_piece` пачками по 1000; после пачки в строке выдела — `read_at` (МСК). Повторный аудит не запрашивает карточку, если `read_at >= сегодня − 2 дня`. Инкремент карточки не пропускает.



## Ограничения и допущения

- Импорт ограничен квотами/лимитами ФГИС, не N реплик fgislk без координации.
- Отправка в ФГИС, XML, PDF и СМЭВ — не это приложение и не в контуре.
- fgislk карту не публикует; пишет таблицы Spatial data.
- Контур из СПД не пишем: колонка `geom` этим процессом не заполняется и при upsert не трогается. WFS — позже.
- HTTPS к порталу: `FGIS_TLS` в `.env`. Пусто — `schannel` на Windows, `openssl` на Linux. `schannel` — только **Windows** `curl.exe` **(Schannel)**, как НСИ в mirror. OpenSSL в Python и Linux-Docker рвут handshake (`error:0A000410`). `openssl` — системный `curl` (`SECLEVEL=1`) или httpx. Запуск к порталу: `fgislk/run.ps1` на хосте. Сервис Compose `fgislk` — профиль `container`, к порталу не ходит.
- Год лесоустройства не маппим.
- Настройки allowlist (`FGIS_MAX_WORKERS`, `FGIS_TLS`, `FGIS_HOST`) можно менять через `PUT /settings`: overlay-файл (`FGISLK_SETTINGS_FILE`, иначе `fgislk-settings.json` в cwd) поверх `.env`. Пул SQLAlchemy с размера на старте не пересобирается. Рестарт без файла возвращает значения `.env`. Секреты и `POSTGRES_*` через API нельзя.



## Интерфейсы

- **ИС ФГИС ЛК:** СПД `taxationPiece/changedOverPeriod` и `taxationPiece/{id}`; заголовки `login` / `password` из `.env`. TLS: `FGIS_TLS` (`schannel` / `openssl`).
- **Postgres:** те же `POSTGRES_`*, запись в `taxation_piece` и `fgis_import_history`.
- **migrate:** `/ready` и `REQUIRED_SCHEMA` перед стартом.
- **HTTP:** `/health`, `/ready`, `/status` (`day` = дата запроса `period_end`, `subject`, `data_kind`; `running` = живые воркеры; при совпадении `period_end` — `in_progress` / `result=running` / период / `updated_count`; прошлый журнал в `last`). `GET /panel` — манифест для admin (колонки, фильтры, пагинация по дате запроса). `GET /history` — журнал `fgis_import_history` (HTTP, не витрина). `GET`/`PUT /settings` — allowlist. Ручные прогоны (порт `FGISLK_PORT`, по умолчанию 8081):
  - все субъекты: `GET http://127.0.0.1:8081/sync?start=1`, `GET http://127.0.0.1:8081/sync?audit=1`, `GET http://127.0.0.1:8081/sync?audit=1&day=2026-08-30`, `GET http://127.0.0.1:8081/sync?stop=1`;
  - один субъект: `GET http://127.0.0.1:8081/sync?start=1&subject=07`, `GET http://127.0.0.1:8081/sync?audit=1&subject=07`, `GET http://127.0.0.1:8081/sync?audit=1&day=2026-08-30&subject=07` (`stop` с `subject=` нельзя).
- **admin:** `/panel`, `/status` (таблица журнала), команды через `/sync`. Форму `/settings` и отдельный журнал `/history` не показывает.
- **Потребители:** общая PostGIS, ключ связи — субъект + учётный номер ФГИС ЛК.



## Архитектура решения

ИС ФГИС ЛК → fgislk (`FGIS_TLS`) → `taxation_piece` + `fgis_import_history`. Модель слоя — `[spatialData/CONTEXT.md](../spatialData/CONTEXT.md)`. Цикл после полуночи МСК и на старте; вручную: `start=1` / `audit=1` / `stop=1`. Advisory lock на субъект в Postgres.