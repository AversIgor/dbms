---
name: restart-service
description: Restarts a dbms process (fgislk, admin, migrate, or Postgres) the way this repo actually runs — host PowerShell for fgislk, Docker Compose for db/migrate/admin. Use when the user asks to restart, reload, поднять заново, or kill-and-start a service, after code or .env changes that need a new process, or when a port is stuck.
---

# Restart service

Read this skill, then execute. Do not invent another launcher. Do not read `README.md`. Do not print `.env` secrets.

## Which process

Infer from the conversation (files just edited, last error). If the user named one — that one only.

| Name | Default port | Typical runtime here |
| --- | --- | --- |
| `fgislk` | `FGISLK_PORT` / 8081 | **Windows host** via `fgislk/run.ps1` (Schannel). Compose service exists only with profile `container`. |
| `admin` | `ADMIN_PORT` / 8082 | Compose, or host `admin/run.ps1` |
| `migrate` | `MIGRATE_PORT` / 8080 | Compose |
| `db` | `POSTGRES_PORT` | Compose only. Restart **only if the user named Postgres/db**. |

Default if they said «сервис» without a name: `fgislk`.

Never `docker compose down` for a single-app restart. Never scale `migrate` or `fgislk`. Never `alembic upgrade` from `fgislk`.

## Detect how it is running

From repo root:

1. `docker compose ps`
2. Listener on the port (PowerShell): `Get-NetTCPConnection -LocalPort <port> -State Listen`
3. If Compose shows the service `Up` **and** it is not `fgislk` on this Windows machine — treat as Compose.
4. If something listens on 8081 and Compose `fgislk` is not running — treat as **host** `fgislk` (the usual case). Closing a terminal does not free the port.

## Host process (usual: fgislk)

Working directory: repo root (so `.env` loads).

1. Optional for `fgislk` if a sync may be running: `GET http://127.0.0.1:<port>/sync?stop=1` (ignore failure if already down).
2. Stop the listener. Use the PID from `Get-NetTCPConnection` (`OwningProcess`), then `Stop-Process -Id <pid> -Force`. If several PIDs — all of them. Wait until the port is free.
3. Start in background with the existing script:

```powershell
powershell.exe -File ./fgislk/run.ps1
```

For host `admin`: `powershell.exe -File ./admin/run.ps1`. There is no `migrate/run.ps1`.

4. Confirm: `GET /ready` for `fgislk` and `migrate`, `GET /health` for `admin`. Success is HTTP 200. If `fgislk` dies immediately, schema mismatch vs `migrate` `/ready` is the first thing to check — do not start `fgislk` by skipping that.

`PUT /settings` overlay (`fgislk-settings.json` in cwd) survives restart; deleting the file returns allowlist values to `.env`.

## Compose process (usual: db, migrate, admin)

Code or Dockerfile changed:

```powershell
docker compose up --build -d <service>
```

Only process restart, same image:

```powershell
docker compose restart <service>
```

`fgislk` in Compose: `docker compose --profile container up --build -d fgislk`. Do not do this on Windows when the host `run.ps1` already owns 8081.

After `migrate` restart, wait until healthy before restarting consumers.

## Report

One short line: what was stopped (PID or container), how it was started, health URL and status. If health failed, the error — not a dump of `.env`.
