"""дата актуальности выдела (taxation_piece.actuality_date).

Revision ID: 0006_actuality_date
Revises: 0005_taxation_piece_read_at
Create Date: 2026-09-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_actuality_date"
down_revision: Union[str, Sequence[str], None] = "0005_taxation_piece_read_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "taxation_piece",
        sa.Column(
            "actuality_date",
            sa.Date(),
            nullable=True,
            comment="дата актуальности (появление в ФГИС ЛК)",
        ),
    )


def downgrade() -> None:
    op.drop_column("taxation_piece", "actuality_date")
