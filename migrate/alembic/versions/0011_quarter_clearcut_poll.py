"""опрос лесосек на квартале.

Revision ID: 0011_quarter_clearcut_poll
Revises: 0010_crs
Create Date: 2026-09-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_quarter_clearcut_poll"
down_revision: Union[str, Sequence[str], None] = "0010_crs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quarters",
        sa.Column(
            "clearcut_polled_at",
            sa.Date(),
            nullable=True,
            comment="дата опроса лесосек",
        ),
    )
    op.add_column(
        "quarters",
        sa.Column(
            "has_clearcuts",
            sa.Boolean(),
            nullable=True,
            comment="есть лесосеки",
        ),
    )
    op.create_index(
        "ix_quarters_subject_clearcut_polled_at",
        "quarters",
        ["subject", "clearcut_polled_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_quarters_subject_clearcut_polled_at", table_name="quarters")
    op.drop_column("quarters", "has_clearcuts")
    op.drop_column("quarters", "clearcut_polled_at")
