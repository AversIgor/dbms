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
docker compose down
foreach ($port in 8080, 8081, 8082, 5433) {
  Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { if ($_ -gt 0) { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue } }
}
```

Запуск с учётом незакрытых сеансов (сначала освобождает те же порты, затем поднимает Compose и fgislk):

```powershell
docker compose down
foreach ($port in 8080, 8081, 8082, 5433) {
  Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { if ($_ -gt 0) { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue } }
}
docker compose up --build -d
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
sudo apt update
sudo apt install -y ca-certificates curl git python3-venv python3-pip
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
```

Выйти из сеанса Ubuntu полностью и зайти снова (группа `docker`). Проверка: `git --version`, `docker compose version`, `docker run --rm hello-world`.

### 2. Клон репозитория

Каталог — домашний, не `/root`.

```bash
cd ~
git clone https://github.com/AversIgor/dbms.git
cd ~/dbms
git status
```

`git status` должен быть чистым. Код на сервере не править и не пушить.

### 3. `.env`

```bash
cd ~/dbms
test -f .env.example && cp .env.example .env
nano .env
chmod 600 .env
```

Задать свои значения (не из разработки): `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST=127.0.0.1`, `POSTGRES_PORT=5433`, `MIGRATE_PORT=8080`, `ADMIN_PORT=8082`, `FGISLK_PORT=8081`, `FGIS_TLS=openssl`, `FGIS_MAX_WORKERS=10`, `FGIS_LOGIN`, `FGIS_PASSWORD`. `FGIS_TLS=openssl` сам по себе handshake не чинит — нужен gost-engine (шаг 5). Для контейнера `migrate` Compose подставляет хост `db` и порт `5432`; для `fgislk` на хосте в файле нужны `127.0.0.1` и проброшенный `POSTGRES_PORT`.

### 4. Compose (`db`, `migrate`, `admin`)

```bash
cd ~/dbms
docker compose up --build -d
docker compose ps
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/ready
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8082/health
```

Оба раза `200`. Данные Postgres — том `pgdata`, переживает `docker compose down`. `migrate` при старте делает `upgrade`. Не масштабировать: параллельный upgrade не запускать.

**Не публиковать Postgres в интернет.** Не открывать снаружи 5433, 8080, 8081, 8082.

Если включаете `ufw` при доступе по **RDP**, сначала разрешите 3389, иначе сеанс отвалится:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 3389/tcp
sudo ufw enable
```

### 5. `fgislk` на хосте

СПД `fgislk.gov.ru` на Linux требует GOST-TLS: обычный curl даёт `error:0A000410:sslv3 alert handshake failure`. На Windows это закрывает Schannel (`fgislk/run.ps1`) — тот путь не трогать. WFS `pub.fgislk.gov.ru` работает обычным TLS.

**Один раз на машине** (не при каждом `git pull`): собрать gost-engine. Движок ставится в систему (`/usr/lib/.../gost.so`), переживает обновление репозитория.

```bash
cd ~/dbms
sudo bash fgislk/install_gost_engine.sh
OPENSSL_CONF=/etc/ssl/fgislk-openssl-gost.cnf openssl engine -t gost
```

Ожидается `(gost) ... [ available ]`. Ветка `master` gost-engine не соберётся (нужен OpenSSL ≥ 3.4); скрипт ставит тег `v3.0.3`. Повторно — только если engine пропал или handshake снова `0A000410`.

```bash
cd ~/dbms
python3 -m venv .venv
. .venv/bin/activate
pip install -e ./fgislk
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
sudo systemctl daemon-reload
sudo systemctl enable --now dbms-fgislk
sudo systemctl status dbms-fgislk
```

Витрина: Firefox на этой Ubuntu → [http://127.0.0.1:8082/](http://127.0.0.1:8082/).

### 6. Nginx + HTTPS (только если витрина нужна из интернета)

При работе через RDP и локальный Firefox этот шаг не нужен. Снаружи только 80/443, не порты приложений.

```bash
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
sudo ln -s /etc/nginx/sites-available/dbms /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d your.domain.ru
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

### 7. Новая версия программы (обновление с GitHub)

На сервере **не коммитить и не править код**. `.env` при `git pull` не затирается (файла нет в git). Локальные правки на виртуалке мешают pull — их не делать.

Порядок: бэкап → новый код → пересборка контейнеров (схема через `migrate`) → переустановка `fgislk` → рестарт процесса → проверка. `install_gost_engine.sh` при обновлении **не** запускать — это шаг один раз при первой выкладке.

```bash
cd ~/dbms

# бэкап БД (том pgdata pull не трогает, но откатить схему без копии нельзя)
set -a && . ./.env && set +a
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > ~/dbms-backup-$(date +%F).sql

git fetch origin
git status
git pull --ff-only origin main

docker compose up --build -d
. .venv/bin/activate
pip install -e ./fgislk
sudo systemctl restart dbms-fgislk

curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/ready
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8081/ready
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8082/health
```

Все три проверки — `200`. `--ff-only`: на сервере не создавать merge-коммиты. Если `pull` отказал — смотреть `git status`, не `git reset --hard`, пока не ясно, что теряется.

Нет systemd: остановить старый `fgislk` (Ctrl+C в том окне) и снова `fgislk serve` из корня `~/dbms` с активным `.venv`.
