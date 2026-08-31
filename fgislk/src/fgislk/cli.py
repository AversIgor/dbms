from __future__ import annotations

import logging

import click
import uvicorn

from fgislk.settings import listen_port, load_settings

load_settings()


@click.group()
def main() -> None:
    """Импорт слоёв ИС ФГИС ЛК в PostGIS."""


@main.command()
@click.option("--host", default="0.0.0.0", show_default=True)
@click.option("--port", type=int, default=None)
def serve(host: str, port: int | None) -> None:
    """HTTP: /health /ready /status /sync?start=1 /sync?audit=1 /sync?audit=1&day= /sync?stop=1."""
    logging.basicConfig(level=logging.INFO)
    if port is None:
        port = listen_port()
    uvicorn.run("fgislk.app:app", host=host, port=port, factory=False)


if __name__ == "__main__":
    main()
