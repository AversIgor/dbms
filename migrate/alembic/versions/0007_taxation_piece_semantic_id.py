"""идентификатор семантики WFS (taxation_piece.semantic_id).

Revision ID: 0007_taxation_piece_semantic_id
Revises: 0006_actuality_date
Create Date: 2026-09-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_taxation_piece_semantic_id"
down_revision: Union[str, Sequence[str], None] = "0006_actuality_date"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "taxation_piece",
        sa.Column(
            "semantic_id",
            sa.Integer(),
            nullable=True,
            comment="идентификатор семантики WFS (TAXATION_PIECE.{id})",
        ),
    )


def downgrade() -> None:
    op.drop_column("taxation_piece", "semantic_id")
