"""дата отвода лесосеки (clearcut.limitation_dt) — date.

Revision ID: 0014_clearcut_limitation_dt
Revises: 0013_fgis_id_unique
Create Date: 2026-09-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_clearcut_limitation_dt"
down_revision: Union[str, Sequence[str], None] = "0013_fgis_id_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TO_DATE = """
CASE
  WHEN limitation_dt IS NULL OR btrim(limitation_dt) = '' THEN NULL
  WHEN btrim(limitation_dt) ~ '^-?[0-9]+$' THEN
    (
      to_timestamp(
        CASE
          WHEN abs(btrim(limitation_dt)::double precision) >= 10000000000
          THEN btrim(limitation_dt)::double precision / 1000.0
          ELSE btrim(limitation_dt)::double precision
        END
      ) AT TIME ZONE 'Europe/Moscow'
    )::date
  WHEN btrim(limitation_dt) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN
    left(btrim(limitation_dt), 10)::date
  ELSE NULL
END
"""


def upgrade() -> None:
    op.alter_column(
        "clearcut",
        "limitation_dt",
        existing_type=sa.String(length=20),
        type_=sa.Date(),
        existing_nullable=True,
        existing_comment="дата отвода",
        postgresql_using=_TO_DATE,
    )


def downgrade() -> None:
    op.alter_column(
        "clearcut",
        "limitation_dt",
        existing_type=sa.Date(),
        type_=sa.String(length=20),
        existing_nullable=True,
        existing_comment="дата отвода",
        postgresql_using="limitation_dt::text",
    )
