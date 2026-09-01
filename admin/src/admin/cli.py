from __future__ import annotations

import click
import uvicorn

from admin.settings import listen_port, load_settings

load_settings()


@click.group()
def main() -> None:
    """Витрина HTTP разделов для оператора."""


@main.command()
@click.option("--host", default="0.0.0.0", show_default=True)
@click.option("--port", type=int, default=None)
def serve(host: str, port: int | None) -> None:
    """HTTP: / /health /catalog /p/{id}/…"""
    if port is None:
        port = listen_port()
    uvicorn.run("admin.app:app", host=host, port=port, factory=False)


if __name__ == "__main__":
    main()
