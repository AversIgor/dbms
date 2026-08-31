"""выдел (taxation_piece).

Revision ID: 0002_taxation_piece
Revises: 0001_postgis
Create Date: 2026-08-31
"""

from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "0002_taxation_piece"
down_revision: Union[str, Sequence[str], None] = "0001_postgis"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "taxation_piece",
        sa.Column(
            "fgis_id",
            sa.String(length=50),
            nullable=False,
            comment="учётный номер выдела ФГИС ЛК",
        ),
        sa.Column("subject", sa.String(length=3), nullable=False, comment="субъект"),
        sa.Column(
            "taxation_piece",
            sa.String(length=10),
            nullable=True,
            comment="номер выдела",
        ),
        sa.Column("quarter", sa.String(length=20), nullable=True, comment="номер квартала"),
        sa.Column("area", sa.Numeric(precision=16, scale=5), nullable=True, comment="площадь"),
        sa.Column("status", sa.String(length=10), nullable=True, comment="status"),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(geometry_type="GEOMETRY", spatial_index=False),
            nullable=True,
            comment="контур",
        ),
        sa.PrimaryKeyConstraint("subject", "fgis_id", name="taxation_piece_pkey"),
        comment="выдел",
    )
    op.create_index("ix_taxation_piece_fgis_id", "taxation_piece", ["fgis_id"])
    op.create_index("ix_taxation_piece_subject", "taxation_piece", ["subject"])
    op.create_index(
        "ix_taxation_piece_geom",
        "taxation_piece",
        ["geom"],
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_index("ix_taxation_piece_geom", table_name="taxation_piece")
    op.drop_index("ix_taxation_piece_subject", table_name="taxation_piece")
    op.drop_index("ix_taxation_piece_fgis_id", table_name="taxation_piece")
    op.drop_table("taxation_piece")
