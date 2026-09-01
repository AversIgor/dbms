# dbms

Несколько приложений, одна PostgreSQL 16 + PostGIS. Схема меняет только `migrate`.

Для агента: `[AGENTS.md](AGENTS.md)` — карта разделов, не читать весь репозиторий. Схема: `[migrate/CONTEXT.md](migrate/CONTEXT.md)`. Архитектура: `[Архитектура.md](Архитектура.md)`.

Настройки БД — только в `.env` (шаблон `.env.example`, в git не попадает). Compose и `migrate` читают их оттуда.

## Запуск и остановка

Из корня репозитория:

```powershell
copy .env.example .env
docker compose up --build -d
```

Поднимаются БД (`db`, порт из `POSTGRES_PORT`), `migrate` (порт из `MIGRATE_PORT`) и `admin` (порт `ADMIN_PORT`, по умолчанию 8082). Страница схемы: [http://127.0.0.1:8080/](http://127.0.0.1:8080/). Витрина разделов: [http://127.0.0.1:8082/](http://127.0.0.1:8082/)

Импорт выделов на **Windows-хосте** (`FGIS_TLS=schannel`, `curl.exe` / Schannel; Linux-контейнер OpenSSL к порталу handshake не проходит):

```powershell
docker compose up --build -d
.\fgislk\run.ps1
```

В Git Bash / WSL PowerShell-путь `.\fgislk\run.ps1` не работает. Из корня:

```bash
powershell.exe -File ./fgislk/run.ps1
```

Витрина на хосте (если не из Compose): `.\admin\run.ps1` — [http://127.0.0.1:8082/](http://127.0.0.1:8082/).

Витрина (статус, команды, журнал, настройки): [http://127.0.0.1:8082/](http://127.0.0.1:8082/) (`FGISLK_URL` с хоста — `http://127.0.0.1:8081`). Прямые GET по-прежнему работают:  
Статус: [http://127.0.0.1:8081/status](http://127.0.0.1:8081/status)  
Старт инкремента: [http://127.0.0.1:8081/sync?start=1](http://127.0.0.1:8081/sync?start=1)  
Аудит: [http://127.0.0.1:8081/sync?audit=1](http://127.0.0.1:8081/sync?audit=1)  
Аудит с даты: [http://127.0.0.1:8081/sync?audit=1&day=2026-08-30](http://127.0.0.1:8081/sync?audit=1&day=2026-08-30)  
Стоп прогона: [http://127.0.0.1:8081/sync?stop=1](http://127.0.0.1:8081/sync?stop=1)

Закрыть окно терминала недостаточно: `python -m fgislk serve` остаётся на 8081. Остановить именно его, затем снова `run.ps1`:

```powershell
Get-NetTCPConnection -LocalPort 8081 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
.\fgislk\run.ps1
```

Проверка, кто слушает порт:

```powershell
netstat -ano | grep 8081
```

Статус:

```powershell
docker compose ps
```

Остановить контейнеры (не удалять):

```powershell
docker compose stop
```

Остановить и удалить контейнеры (том `pgdata` с данными БД сохраняется):

```powershell
docker compose down
```

Если порт 8080 занят старым контейнером:

```powershell
docker rm -f dbms-lk-migrate-1
```



## Публикация на виртуальном сервере

На VPS поднимаются те же сервисы: PostgreSQL 16 + PostGIS (`db`), `migrate` (страница схемы и миграции) и `admin` (витрина оператора, не публиковать снаружи без необходимости). Прикладной UI, XML, PDF и СМЭВ в контур не входят.

### Сервер

Ubuntu 22.04/24.04 или Debian, Docker Engine + Compose plugin, git. Снаружи открыть SSH (22) и, если будет HTTPS, 80/443.

```bash
sudo apt update
sudo apt install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

Перелогиниться, затем `docker compose version`.

### Код и `.env`

```bash
git clone <url-репозитория> dbms
cd dbms
cp .env.example .env
nano .env
```

На проде задать сильный `POSTGRES_PASSWORD` (не оставлять `lk` / `lk`). `.env` в git не входит — создавать на сервере. `POSTGRES_HOST` в файле может быть `127.0.0.1`: Compose для контейнера `migrate` подставляет хост `db`.

**Не публиковать Postgres в интернет.** В `compose.yaml` порт БД проброшен на хост (`POSTGRES_PORT`, в примере 5433). Снаружи достаточно HTTP(S). Порт 5433 закрыть файрволом или убрать `ports` у сервиса `db`, если с хоста к БД не ходите.

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Не открывать 5433 и 8080 снаружи, если стоит nginx.

### Запуск

```bash
docker compose up --build -d
docker compose ps
curl -sS http://127.0.0.1:8080/ready
```

Страница схемы: `http://<IP-сервера>:8080/` — только если порт 8080 открыт. Для публикации лучше nginx на 80/443.

Данные Postgres живут в томе `pgdata` и переживают `docker compose down`. `migrate` при старте делает `upgrade` (`migrate serve --upgrade`). Не масштабировать: параллельный upgrade не запускать.

### Nginx + HTTPS

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

`/etc/nginx/sites-available/dbms`:

```nginx
server {
    listen 80;
    server_name your.domain.ru;

    location / {
        proxy_pass http://127.0.0.1:8080;
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

Снаружи только 80/443; `MIGRATE_PORT` слушает localhost.

### Обновление и бэкап

```bash
cd dbms
git pull
docker compose up --build -d
```

Бэкап БД: `docker compose exec db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"` (пользователь и имя БД — из `.env`).