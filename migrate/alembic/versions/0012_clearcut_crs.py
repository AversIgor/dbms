"""система координат СПД (clearcut.crs).

Revision ID: 0012_clearcut_crs
Revises: 0011_quarter_clearcut_poll
Create Date: 2026-09-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_clearcut_crs"
down_revision: Union[str, Sequence[str], None] = "0011_quarter_clearcut_poll"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "clearcut",
        sa.Column(
            "crs",
            sa.String(length=50),
            nullable=True,
            comment="система координат СПД",
        ),
    )


def downgrade() -> None:
    op.drop_column("clearcut", "crs")
