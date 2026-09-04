from __future__ import annotations

import logging

import click
import uvicorn

from api.settings import listen_port, load_settings

load_settings()


@click.group()
def main() -> None:
    """Read-only HTTP для внешних ИС."""


@main.command()
@click.option("--host", default="0.0.0.0", show_default=True)
@click.option("--port", type=int, default=None)
def serve(host: str, port: int | None) -> None:
    """HTTP: /health /ready /panel /status /getListQuarters."""
    logging.basicConfig(level=logging.INFO)
    if port is None:
        port = listen_port()
    uvicorn.run("api.app:app", host=host, port=port, factory=False)


if __name__ == "__main__":
    main()
