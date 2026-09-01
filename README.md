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



## Публикация на виртуальном сервере

На VPS поднимаются те же сервисы: PostgreSQL 16 + PostGIS (`db`), `migrate` (миграция схемы, `/ready`) и `admin` (витрина оператора, не публиковать снаружи без необходимости). Прикладной UI, XML, PDF и СМЭВ в контур не входят.

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

Не открывать 5433, 8080 и 8082 снаружи, если стоит nginx.

### Запуск

```bash
docker compose up --build -d
docker compose ps
curl -sS http://127.0.0.1:8080/ready
```

Витрина: `http://<IP-сервера>:8082/` — только если порт 8082 открыт. Для публикации лучше nginx на 80/443.

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

Снаружи только 80/443; `MIGRATE_PORT` и `ADMIN_PORT` слушают localhost.

### Обновление и бэкап

```bash
cd dbms
git pull
docker compose up --build -d
```

Бэкап БД: `docker compose exec db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"` (пользователь и имя БД — из `.env`).