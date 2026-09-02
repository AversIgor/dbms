# dbms

Несколько приложений, одна PostgreSQL 16 + PostGIS. Схема меняет только `migrate`.

Для агента: `[AGENTS.md](AGENTS.md)` — карта разделов, не читать весь репозиторий. Схема: `[migrate/CONTEXT.md](migrate/CONTEXT.md)`. Архитектура: `[Архитектура.md](Архитектура.md)`.

Настройки БД — только в `.env` (шаблон `.env.example`, в git не попадает). Compose и `migrate` читают их оттуда.

## Запуск и остановка

Из корня репозитория. Первый раз: `copy .env.example .env`.

Поднимаются БД (`db`, порт из `POSTGRES_PORT`, в примере 5433), `migrate` (`MIGRATE_PORT`, 8080) и `admin` (`ADMIN_PORT`, 8082). Импорт выделов — на **Windows-хосте** (`FGIS_TLS=schannel`; Linux-контейнер OpenSSL к порталу handshake не проходит): `powershell.exe -File ./fgislk/run.ps1` (порт 8081). Закрыть окно терминала недостаточно: процесс на порту остаётся.

Витрина (статус, команды, журнал, настройки): [http://127.0.0.1:8082/](http://127.0.0.1:8082/). Витрина на хосте вместо Compose: `.\admin\run.ps1`.

Полная остановка контейнеров, процессов на хосте и БД (том `pgdata` с данными сохраняется):

```powershell
# остановить контейнеры db / migrate / admin (данные Postgres в томе остаются)
docker compose down
# закрыть процессы на портах Windows: 8080 migrate, 8081 fgislk, 8082 admin, 5433 БД
foreach ($port in 8080, 8081, 8082, 5433) {
  Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { if ($_ -gt 0) { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue } }
}
```

Запуск с учётом незакрытых сеансов (сначала освобождает те же порты, затем поднимает Compose и fgislk):

```powershell
# остановить контейнеры (данные БД не удаляются)
docker compose down
# освободить порты, если после закрытия окна процесс ещё жив
foreach ($port in 8080, 8081, 8082, 5433) {
  Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { if ($_ -gt 0) { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue } }
}
# собрать и запустить контейнеры db / migrate / admin
docker compose up --build -d
# запустить импорт fgislk на этом Windows-ПК (порт 8081)
powershell.exe -File ./fgislk/run.ps1
```

Статус контейнеров: `docker compose ps`. Кто слушает порт: `Get-NetTCPConnection -LocalPort 8081 -State Listen`.

## Публикация на пустой Ubuntu

Одна виртуалка Ubuntu 22.04/24.04 (лучше 24.04). Вход по **RDP** (рабочий стол) или SSH, обычный пользователь с `sudo`. Код только из git, не копировать папку с Windows.

На сервере: `db`, `migrate`, `admin` — Docker Compose; `fgislk` — **на хосте** (`FGIS_TLS=openssl` и gost-engine). Профиль Compose `container` для fgislk не использовать. Витрину снаружи без нужды не открывать: при RDP достаточно Firefox **на этой Ubuntu** → [http://127.0.0.1:8082/](http://127.0.0.1:8082/).

Репозиторий публичный: `https://github.com/AversIgor/dbms.git`, ветка `main`. `.env` и `fgislk-settings.json` в git нет — после clone их создаёте сами, секреты не коммитить.

Команды — в терминале Ubuntu (**Ctrl+Alt+T**). Вставка: **Ctrl+Shift+V**. Сначала: `whoami` и `echo $HOME` — имя и путь подставляйте в systemd. Нужен Python **3.12+** (`python3 --version`). На 22.04, если 3.10: `sudo add-apt-repository -y ppa:deadsnakes/ppa && sudo apt install -y python3.12 python3.12-venv`, дальше `python3.12` вместо `python3`.

### 1. Пакеты и Docker

```bash
# обновить список пакетов Ubuntu
sudo apt update
# поставить git, Python и инструменты для HTTPS
sudo apt install -y ca-certificates curl git python3-venv python3-pip
# установить Docker официальным скриптом
curl -fsSL https://get.docker.com | sudo sh
# разрешить текущему пользователю запускать docker без sudo
sudo usermod -aG docker "$USER"
```

Выйти из сеанса Ubuntu полностью и зайти снова (группа `docker`). Проверка: `git --version`, `docker compose version`, `docker run --rm hello-world`.

### 2. Клон репозитория

Каталог — домашний, не `/root`.

```bash
# перейти в домашнюю папку
cd ~
# скачать код с GitHub в ~/dbms
git clone https://github.com/AversIgor/dbms.git
# зайти в папку проекта
cd ~/dbms
# проверить: дерево должно быть чистым, без своих правок
git status
```

`git status` должен быть чистым. Код на сервере не править и не пушить.

### 3. `.env`

```bash
# перейти в папку проекта
cd ~/dbms
# если есть шаблон — скопировать его в .env (секреты, файл не в git)
test -f .env.example && cp .env.example .env
# открыть .env в редакторе и заполнить логины/пароли
nano .env
# закрыть файл от чужого чтения
chmod 600 .env
```

Задать свои значения (не из разработки): `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST=127.0.0.1`, `POSTGRES_PORT=5433`, `MIGRATE_PORT=8080`, `ADMIN_PORT=8082`, `FGISLK_PORT=8081`, `FGIS_TLS=openssl`, `FGIS_MAX_WORKERS=10`, `FGIS_LOGIN`, `FGIS_PASSWORD`. `FGIS_TLS=openssl` сам по себе handshake не чинит — нужен gost-engine (шаг 5). Для контейнера `migrate` Compose подставляет хост `db` и порт `5432`; для `fgislk` на хосте в файле нужны `127.0.0.1` и проброшенный `POSTGRES_PORT`.

### 4. Compose (`db`, `migrate`, `admin`)

```bash
# перейти в папку проекта
cd ~/dbms
# собрать и запустить контейнеры db / migrate / admin в фоне
docker compose up --build -d
# показать статус контейнеров
docker compose ps
# проверка migrate: должно быть 200
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/ready
# проверка admin: должно быть 200
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8082/health
```

Оба раза `200`. Данные Postgres — том `pgdata`, переживает `docker compose down`. `migrate` при старте делает `upgrade`. Не масштабировать: параллельный upgrade не запускать.

**Не публиковать Postgres в интернет.** Не открывать снаружи 5433, 8080, 8081, 8082.

Если включаете `ufw` при доступе по **RDP**, сначала разрешите 3389, иначе сеанс отвалится:

```bash
# не потерять SSH после включения фаервола
sudo ufw allow OpenSSH
# не потерять удалённый рабочий стол (RDP)
sudo ufw allow 3389/tcp
# включить фаервол
sudo ufw enable
```

### 5. `fgislk` на хосте

СПД `fgislk.gov.ru` на Linux требует GOST-TLS: обычный curl даёт `error:0A000410:sslv3 alert handshake failure`. На Windows это закрывает Schannel (`fgislk/run.ps1`) — тот путь не трогать.

**Один раз на машине** (не при каждом `git pull`): собрать gost-engine. Движок ставится в систему (`/usr/lib/.../gost.so`), переживает обновление репозитория.

```bash
# перейти в папку проекта
cd ~/dbms
# один раз: собрать GOST-движок для TLS к ФГИС ЛК
sudo bash fgislk/install_gost_engine.sh
# проверить, что handshake к порталу проходит (пароль не печатает)
bash fgislk/check_fgis_tls.sh
```

Нужны строки `**OK` у engine** и `**http=200` на `/rmdl/`**. Пока скрипт пишет `FAIL` — витрина будет с `0A000410`; тогда сначала снова `sudo bash fgislk/install_gost_engine.sh`, `fgislk` не поднимать. Ветка `master` gost-engine не соберётся (нужен OpenSSL ≥ 3.4); скрипт ставит тег `v3.0.3`. Повторно — только если engine пропал или handshake снова `0A000410`.

Проверка доступности ФГИС ЛК (пароль не печатает) — тот же `check_fgis_tls.sh`. 

```bash
# перейти в папку проекта
cd ~/dbms
# создать виртуальное окружение Python
python3 -m venv .venv
# включить это окружение (в приглашении появится (.venv))
. .venv/bin/activate
# поставить пакет fgislk в окружение
pip install -e ./fgislk
# запустить импорт (процесс живёт, пока открыто это окно)
fgislk serve
```

Не `python -m fgislk serve` (нужен `__main__.py`, его может не быть в клоне). Запасной вариант: `python -m fgislk.cli serve`. Каталог — корень репозитория, чтобы подхватить `.env`.

Проверка (другое окно): `curl -sS http://127.0.0.1:8081/ready`. Compose `admin` ходит на `http://host.docker.internal:8081`.

Чтобы процесс жил после logout — systemd (подставить своего пользователя и путь):

```ini
# /etc/systemd/system/dbms-fgislk.service
[Unit]
Description=dbms fgislk
After=docker.service network-online.target
Wants=network-online.target

[Service]
User=igor
WorkingDirectory=/home/igor/dbms
Environment=PATH=/home/igor/dbms/.venv/bin:/usr/bin
ExecStart=/home/igor/dbms/.venv/bin/fgislk serve
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
# перечитать unit-файлы systemd после создания dbms-fgislk.service
sudo systemctl daemon-reload
# включить автозапуск и сразу стартовать fgislk
sudo systemctl enable --now dbms-fgislk
# показать, жива ли служба
sudo systemctl status dbms-fgislk
```

Витрина: Firefox на этой Ubuntu → [http://127.0.0.1:8082/](http://127.0.0.1:8082/).

### 6. Nginx + HTTPS (только если витрина нужна из интернета)

При работе через RDP и локальный Firefox этот шаг не нужен. Снаружи только 80/443, не порты приложений.

```bash
# поставить веб-сервер и выпуск HTTPS-сертификата
sudo apt install -y nginx certbot python3-certbot-nginx
```

`/etc/nginx/sites-available/dbms` (витрина admin, не порт migrate):

```nginx
server {
    listen 80;
    server_name your.domain.ru;

    location / {
        proxy_pass http://127.0.0.1:8082;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# включить сайт nginx (ссылка в sites-enabled)
sudo ln -s /etc/nginx/sites-available/dbms /etc/nginx/sites-enabled/
# проверить конфиг и применить без простоя
sudo nginx -t && sudo systemctl reload nginx
# получить сертификат Let's Encrypt (подставить свой домен)
sudo certbot --nginx -d your.domain.ru
# открыть HTTP снаружи
sudo ufw allow 80/tcp
# открыть HTTPS снаружи
sudo ufw allow 443/tcp
```

### 7. Новая версия программы (обновление с GitHub)

На сервере **не коммитить и не править код**. `.env` при `git pull` не затирается (файла нет в git). Локальные правки на виртуалке мешают pull — их не делать.

Порядок: бэкап → стоп процессов → новый код → пересборка контейнеров (схема через `migrate`) → переустановка `fgislk` → старт процесса → проверка. `install_gost_engine.sh` при обновлении **не** запускать — это шаг один раз при первой выкладке.

```bash
# перейти в папку проекта
cd ~/dbms

# подгрузить пароль БД из .env (в историю команд не попадает)
set -a && . ./.env && set +a
# сохранить копию БД в файл ~/dbms-backup-ГГГГ-ММ-ДД.sql
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > ~/dbms-backup-$(date +%F).sql

# остановить импорт fgislk (служба systemd); если службы нет — не ошибка
sudo systemctl stop dbms-fgislk 2>/dev/null || true
# остановить контейнеры db / migrate / admin (данные Postgres в томе остаются)
docker compose down
# убить всё, что ещё слушает порты системы (8080 migrate, 8081 fgislk, 8082 admin, 5433 БД)
for p in 8080 8081 8082 5433; do
  sudo fuser -k "${p}/tcp" 2>/dev/null || true
done
# проверить: список должен быть пустой (порты свободны)
ss -lptn "sport = :8080 or sport = :8081 or sport = :8082 or sport = :5433"

# репозиторий публичный: логин GitHub не нужен; сбросить URL без сохранённого имени
git remote set-url origin https://github.com/AversIgor/dbms.git
# скачать список коммитов без запроса пароля (не вводить пароль от github.com — будет 401)
GIT_TERMINAL_PROMPT=0 git fetch origin
# показать, чистое ли дерево (не должно быть своих правок)
git status
# взять новую версию с ветки main без merge-коммита
git pull --ff-only origin main

# собрать и запустить контейнеры заново (migrate применит схему)
docker compose up --build -d
# включить виртуальное окружение Python
. .venv/bin/activate
# поставить обновлённый пакет fgislk в это окружение
pip install -e ./fgislk
# запустить импорт fgislk снова
sudo systemctl restart dbms-fgislk

# проверка migrate: в ответе должно быть 200
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/ready
# проверка fgislk: 200
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8081/ready
# проверка admin: 200
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8082/health
```

Все три проверки — `200`. `--ff-only`: на сервере не создавать merge-коммиты. Если `pull` отказал — смотреть `git status`, не `git reset --hard`, пока не ясно, что теряется.

Если `fetch`/`pull` пишет `HTTP 401` и спрашивает `Password for 'https://…@github.com'`: **пароль аккаунта GitHub сюда не подходит**. Репозиторий публичный — сначала команды с `set-url` и `GIT_TERMINAL_PROMPT=0` выше; в запросе имени нажать Ctrl+C, не вводить логин.

Нужен вход (репозиторий закрыли или GitHub всё равно требует авторизацию) — **personal access token**, не пароль сайта.

1. В браузере: github.com → свой профиль → **Settings** → **Developer settings** (внизу слева) → **Personal access tokens** → **Tokens (classic)** → **Generate new token (classic)**.
2. Note — любое имя, например `dbms-server`. Срок — по желанию. Галка **`public_repo`** (публичный репозиторий) или **`repo`** (если сделаете закрытым). Generate token → **скопировать сразу** (`ghp_…`). Повторно строку GitHub не покажет.
3. На сервере, когда git спросит: `Username` — логин GitHub (`AversIgor`); `Password` — **вставить токен** `ghp_…`, Enter. Символы на экране не видны — так и должно быть.
4. Чтобы не спрашивал каждый раз (токен в домашнем файле, **не коммитить**):

```bash
# git запомнит токен после первого успешного pull
git config --global credential.helper store
# файл только для вашего пользователя
chmod 600 ~/.git-credentials 2>/dev/null || true
```

Токен в чат, в README и в git не класть. Отозвать: тот же экран Tokens (classic) → Delete.

Нет systemd: остановить старый `fgislk` (Ctrl+C в том окне) и снова `fgislk serve` из корня `~/dbms` с активным `.venv`.

### 8. После перезагрузки Ubuntu

Код и `.env` не трогать. `install_gost_engine.sh` не запускать. Порядок: Compose → дождаться `migrate` → `fgislk`. Стартовать `fgislk` до `200` на `/ready` нельзя: упадёт с `SchemaMismatch` / `Server disconnected`.

```bash
# перейти в папку проекта
cd ~/dbms
# поднять контейнеры (без пересборки образов)
docker compose up -d
# дождаться Up (healthy) у db / migrate / admin
docker compose ps
```

`db`, `migrate`, `admin` — `Up (healthy)`. Том `pgdata` после reboot поднимается не сразу.

```bash
# migrate готов только при 200; иначе подождать и повторить
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/ready
```

Только `200`. Иначе подождать и снова `curl`; не помогло: `docker compose logs --tail=80 migrate`.

```bash
# запустить импорт fgislk (после 200 на migrate)
sudo systemctl start dbms-fgislk
# убедиться, что служба active
sudo systemctl status dbms-fgislk
```

Нет systemd:

```bash
# перейти в папку проекта
cd ~/dbms
# включить Python-окружение
. .venv/bin/activate
# запустить импорт вручную (окно не закрывать)
fgislk serve
```

Все три — `200`:

```bash
# проверка migrate: 200
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/ready
# проверка fgislk: 200
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8081/ready
# проверка admin: 200
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8082/health
```

Витрина: Firefox на этой Ubuntu → [http://127.0.0.1:8082/](http://127.0.0.1:8082/). Чтобы `fgislk` поднимался сам: `sudo systemctl enable --now dbms-fgislk` (unit из шага 5). Compose с `restart: unless-stopped` после reboot обычно уже `Up`.