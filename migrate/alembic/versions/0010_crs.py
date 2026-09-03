"""система координат СПД (taxation_piece.crs, quarters.crs).

Revision ID: 0010_crs
Revises: 0009_clearcut
Create Date: 2026-09-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_crs"
down_revision: Union[str, Sequence[str], None] = "0009_clearcut"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "taxation_piece",
        sa.Column(
            "crs",
            sa.String(length=50),
            nullable=True,
            comment="система координат СПД",
        ),
    )
    op.add_column(
        "quarters",
        sa.Column(
            "crs",
            sa.String(length=50),
            nullable=True,
            comment="система координат СПД",
        ),
    )


def downgrade() -> None:
    op.drop_column("quarters", "crs")
    op.drop_column("taxation_piece", "crs")
