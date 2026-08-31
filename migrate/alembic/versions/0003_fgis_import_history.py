"""история импорта fgislk (fgis_import_history).

Revision ID: 0003_fgis_import_history
Revises: 0002_taxation_piece
Create Date: 2026-08-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_fgis_import_history"
down_revision: Union[str, Sequence[str], None] = "0002_taxation_piece"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fgis_import_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("subject", sa.String(length=3), nullable=False, comment="субъект"),
        sa.Column(
            "day",
            sa.Date(),
            nullable=False,
            comment="последний день закрытого окна",
        ),
        sa.Column("result", sa.String(length=16), nullable=False, comment="ok / error"),
        sa.Column(
            "updated_count",
            sa.Integer(),
            nullable=False,
            comment="сколько строк upsert",
        ),
        sa.Column("data_kind", sa.String(length=32), nullable=False, comment="вид данных"),
        sa.Column("error", sa.Text(), nullable=True, comment="текст ошибки"),
        sa.Column(
            "ran_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="когда записали",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="история импорта fgislk",
    )
    op.create_index(
        "ix_fgis_import_history_subject_kind_day",
        "fgis_import_history",
        ["subject", "data_kind", "day"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fgis_import_history_subject_kind_day",
        table_name="fgis_import_history",
    )
    op.drop_table("fgis_import_history")
