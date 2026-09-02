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

С нуля: одна виртуалка Ubuntu 22.04/24.04, вход по SSH, обычный пользователь с `sudo`. Код только из git (не scp/zip каталога разработки). На сервере поднимаются `db`, `migrate`, `admin` (Compose) и `fgislk` **на хосте** (`FGIS_TLS=openssl`). Профиль Compose `container` для fgislk к порталу не использовать: handshake в Linux-Docker к ФГИС не проходит. Прикладной UI, XML, PDF и СМЭВ в контур не входят. Витрину `admin` снаружи без необходимости не открывать.

Репозиторий: `https://github.com/AversIgor/dbms.git` (SSH: `git@github.com:AversIgor/dbms.git`). Ветка по умолчанию — `main`. `.env` и `fgislk-settings.json` в git не входят: после clone их нет, секреты на сервере не коммитить.

### 1. Пакеты и Docker

```bash
sudo apt update
sudo apt install -y ca-certificates curl git ufw python3-venv python3-pip
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
```

Выйти из SSH и зайти снова (группа `docker`). Проверка: `git --version`, `docker compose version`.

### 2. Клон репозитория

Каталог кода — домашний, не `/root`. Если репозиторий **приватный**, на сервере нужен доступ только на чтение.

**SSH (предпочтительно).** Deploy key в настройках репозитория GitHub → Deploy keys, только read-only:

```bash
ssh-keygen -t ed25519 -C "dbms-vps" -f ~/.ssh/dbms_deploy -N ""
cat ~/.ssh/dbms_deploy.pub
```

`~/.ssh/config`:

```
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/dbms_deploy
  IdentitiesOnly yes
```

```bash
chmod 600 ~/.ssh/config ~/.ssh/dbms_deploy
ssh -T git@github.com
git clone git@github.com:AversIgor/dbms.git
cd dbms
git status
```

`git status` должен быть чистым. Рабочее дерево на сервере не править «для продакшена» и не пушить с виртуалки.

**HTTPS.** `git clone https://github.com/AversIgor/dbms.git` — для приватного репо personal access token (не пароль аккаунта). Токен в историю оболочки не класть; лучше SSH.

### 3. `.env` и файрвол

Шаблон `.env.example` копируется, если он есть в клоне. Иначе создать `.env` в корне `dbms` (права `600`):

```bash
cd ~/dbms
test -f .env.example && cp .env.example .env
chmod 600 .env
nano .env
```

Обязательно задать (значения — свои, не из разработки): `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST=127.0.0.1`, `POSTGRES_PORT=5433`, `MIGRATE_PORT=8080`, `ADMIN_PORT=8082`, `FGISLK_PORT=8081`, `FGIS_TLS=openssl`, `FGIS_MAX_WORKERS=10`, `FGIS_LOGIN`, `FGIS_PASSWORD`. Для контейнера `migrate` Compose подставляет хост `db` и порт `5432`; в файле для процесса **на хосте** (`fgislk`) нужны `127.0.0.1` и проброшенный `POSTGRES_PORT`.

**Не публиковать Postgres в интернет.** В `compose.yaml` порт БД на хосте. Снаружи — SSH и HTTP(S).

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

Не открывать 5433, 8080, 8081, 8082 снаружи.

### 4. Compose (`db`, `migrate`, `admin`)

```bash
cd ~/dbms
docker compose up --build -d
docker compose ps
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/ready
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8082/health
```

`/ready` — 200, когда схема на `head`. Данные Postgres — том `pgdata`, переживает `docker compose down`. `migrate` при старте делает `upgrade`. Не масштабировать: параллельный upgrade не запускать.

### 5. `fgislk` на хосте

```bash
cd ~/dbms
python3 -m venv .venv
. .venv/bin/activate
pip install -e ./fgislk
# из корня репозитория, чтобы подхватить .env
python -m fgislk serve
```

Проверка: `curl -sS http://127.0.0.1:8081/ready`. Compose `admin` ходит на `http://host.docker.internal:8081`. Чтобы процесс жил после logout — systemd (пользователь тот же, что клонировал репо):

```ini
# /etc/systemd/system/dbms-fgislk.service
[Unit]
Description=dbms fgislk
After=docker.service network-online.target
Wants=network-online.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/dbms
Environment=PATH=/home/ubuntu/dbms/.venv/bin:/usr/bin
ExecStart=/home/ubuntu/dbms/.venv/bin/python -m fgislk serve
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Подставить своего пользователя и путь. Затем `sudo systemctl daemon-reload && sudo systemctl enable --now dbms-fgislk`.

### 6. Nginx + HTTPS

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
```

Снаружи только 80/443.

### 7. Обновление с git и бэкап

На сервере не коммитить. `.env` `git pull` не затирает (файл не в дереве). Локальные правки кода на виртуалке — мешают pull: их не делать.

```bash
cd ~/dbms
git fetch origin
git status
git pull --ff-only origin main
docker compose up --build -d
. .venv/bin/activate
pip install -e ./fgislk
sudo systemctl restart dbms-fgislk   # если включён unit
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/ready
```

`--ff-only`: не создавать merge-коммиты на сервере. Если pull отказал — разобрать `git status`, не `reset --hard`, пока не ясно, что теряется (том БД reset не трогает).

Бэкап БД (имена из `.env`):

```bash
set -a && . ./.env && set +a
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"
```