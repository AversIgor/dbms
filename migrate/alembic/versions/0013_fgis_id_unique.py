"""уникальность пространственных данных по учётному номеру ФГИС ЛК.

Revision ID: 0013_fgis_id_unique
Revises: 0012_clearcut_crs
Create Date: 2026-09-03
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0013_fgis_id_unique"
down_revision: Union[str, Sequence[str], None] = "0012_clearcut_crs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("taxation_piece", "quarters", "clearcut")


def _dedup(table: str) -> None:
    op.execute(
        f"""
        DELETE FROM {table}
        WHERE ctid IN (
            SELECT ctid FROM (
                SELECT ctid,
                       ROW_NUMBER() OVER (
                           PARTITION BY fgis_id
                           ORDER BY read_at DESC NULLS LAST, subject
                       ) AS rn
                FROM {table}
            ) ranked
            WHERE rn > 1
        )
        """
    )


def upgrade() -> None:
    for table in _TABLES:
        _dedup(table)
        op.drop_constraint(f"{table}_pkey", table, type_="primary")
        op.drop_index(f"ix_{table}_fgis_id", table_name=table)
        op.create_primary_key(f"{table}_pkey", table, ["fgis_id"])


def downgrade() -> None:
    for table in _TABLES:
        op.drop_constraint(f"{table}_pkey", table, type_="primary")
        op.create_index(f"ix_{table}_fgis_id", table, ["fgis_id"])
        op.create_primary_key(f"{table}_pkey", table, ["subject", "fgis_id"])
