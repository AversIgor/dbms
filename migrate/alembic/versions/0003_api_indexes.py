"""индексы выборок api (участковое / квартал / выдел / лесосека).

Revision ID: 0003_api_indexes
Revises: 0002_constant
Create Date: 2026-09-04
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0003_api_indexes"
down_revision: Union[str, Sequence[str], None] = "0002_constant"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_quarters_subforestry_quarter",
        "quarters",
        ["subforestry", "quarter"],
    )
    op.create_index(
        "ix_taxation_piece_quarter_piece",
        "taxation_piece",
        ["quarter", "taxation_piece"],
    )
    op.create_index(
        "ix_clearcut_quarter_no_area",
        "clearcut",
        ["quarter", "clearcut_no", "area"],
    )


def downgrade() -> None:
    op.drop_index("ix_clearcut_quarter_no_area", table_name="clearcut")
    op.drop_index("ix_taxation_piece_quarter_piece", table_name="taxation_piece")
    op.drop_index("ix_quarters_subforestry_quarter", table_name="quarters")
