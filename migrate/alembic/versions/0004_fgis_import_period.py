"""окно СПД в журнале импорта (period_start / period_end).

Revision ID: 0004_fgis_import_period
Revises: 0003_fgis_import_history
Create Date: 2026-08-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_fgis_import_period"
down_revision: Union[str, Sequence[str], None] = "0003_fgis_import_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "fgis_import_history",
        sa.Column(
            "period_start",
            sa.Date(),
            nullable=True,
            comment="начало окна СПД",
        ),
    )
    op.add_column(
        "fgis_import_history",
        sa.Column(
            "period_end",
            sa.Date(),
            nullable=True,
            comment="конец окна СПД",
        ),
    )


def downgrade() -> None:
    op.drop_column("fgis_import_history", "period_end")
    op.drop_column("fgis_import_history", "period_start")
