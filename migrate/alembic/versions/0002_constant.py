"""таблица constant и сид прикладных ключей из env.

Revision ID: 0002_constant
Revises: 0001_initial
Create Date: 2026-09-04
"""

from __future__ import annotations

import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_constant"
down_revision: Union[str, Sequence[str], None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SEED = (
    ("FGIS_HOST", "string", "Хост СПД", "fgislk.gov.ru"),
    ("FGIS_TLS", "string", "TLS СПД (schannel / openssl, пусто — по ОС)", ""),
    ("FGIS_MAX_WORKERS", "number", "Субъектов сразу", "5"),
    ("FGIS_BATCH_WORKERS", "number", "Пачек карточек внутри субъекта", "3"),
    ("FGIS_LOGIN", "string", "Логин СПД", ""),
    ("FGIS_PASSWORD", "string", "Пароль СПД", ""),
)


def _seed_value(key: str, default: str) -> str:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    return raw


def upgrade() -> None:
    op.create_table(
        "constant",
        sa.Column("key", sa.String(length=64), nullable=False, comment="ключ"),
        sa.Column(
            "kind",
            sa.String(length=16),
            nullable=False,
            comment="string / number / date / boolean",
        ),
        sa.Column("value", sa.Text(), nullable=False, comment="каноническая запись"),
        sa.Column("title", sa.String(length=200), nullable=True, comment="подпись"),
        sa.CheckConstraint(
            "kind IN ('string', 'number', 'date', 'boolean')",
            name="constant_kind_check",
        ),
        sa.PrimaryKeyConstraint("key"),
        comment="прикладные константы",
    )
    table = sa.table(
        "constant",
        sa.column("key", sa.String),
        sa.column("kind", sa.String),
        sa.column("value", sa.Text),
        sa.column("title", sa.String),
    )
    op.bulk_insert(
        table,
        [
            {
                "key": key,
                "kind": kind,
                "value": _seed_value(key, default),
                "title": title,
            }
            for key, kind, title, default in _SEED
        ],
    )


def downgrade() -> None:
    op.drop_table("constant")
