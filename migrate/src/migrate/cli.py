from __future__ import annotations

import os

import click
import uvicorn

from migrate.db import load_settings
from migrate.schema import run_current, run_downgrade, run_history, run_revision, run_upgrade

load_settings()


@click.group()
def main() -> None:
    """Схема PostgreSQL/PostGIS. Единственный Alembic в контуре."""


@main.command()
def upgrade() -> None:
    """alembic upgrade head. Выкладка (Compose), не кнопка в UI."""
    revision = run_upgrade()
    click.echo(f"head: {revision}")


@main.command()
def current() -> None:
    """Текущая revision в alembic_version."""
    run_current()


@main.command()
def history() -> None:
    """Цепочка revision."""
    run_history()


@main.command()
@click.option("--upgrade/--no-upgrade", "do_upgrade", default=False, help="Сначала upgrade head (тот же процесс).")
@click.option("--host", default="0.0.0.0", show_default=True)
@click.option("--port", type=int, default=None)
def serve(do_upgrade: bool, host: str, port: int | None) -> None:
    """HTTP после upgrade: /health /ready /schema и страница статуса."""
    if do_upgrade:
        run_upgrade()
    if port is None:
        port = int(os.environ.get("MIGRATE_PORT", "8080"))
    uvicorn.run("migrate.app:app", host=host, port=port, factory=False)


@main.command()
@click.argument("target")
def downgrade(target: str) -> None:
    """Только вручную, не в автодеплое и не в UI."""
    run_downgrade(target)


@main.command()
@click.option("-m", "--message", required=True)
@click.option("--autogenerate/--no-autogenerate", default=True)
def revision(message: str, autogenerate: bool) -> None:
    """На машине разработчика: models.py → файл в alembic/versions/."""
    run_revision(message, autogenerate)


if __name__ == "__main__":
    main()
