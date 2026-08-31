"""дата чтения выдела из СПД (taxation_piece.read_at).

Revision ID: 0005_taxation_piece_read_at
Revises: 0004_fgis_import_period
Create Date: 2026-08-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_taxation_piece_read_at"
down_revision: Union[str, Sequence[str], None] = "0004_fgis_import_period"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "taxation_piece",
        sa.Column("read_at", sa.Date(), nullable=True, comment="дата чтения из СПД"),
    )
    op.create_index(
        "ix_taxation_piece_subject_read_at",
        "taxation_piece",
        ["subject", "read_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_taxation_piece_subject_read_at", table_name="taxation_piece")
    op.drop_column("taxation_piece", "read_at")
