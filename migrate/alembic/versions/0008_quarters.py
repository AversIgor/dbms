"""квартал (quarters).

Revision ID: 0008_quarters
Revises: 0007_taxation_piece_semantic_id
Create Date: 2026-09-02
"""

from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "0008_quarters"
down_revision: Union[str, Sequence[str], None] = "0007_taxation_piece_semantic_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quarters",
        sa.Column(
            "fgis_id",
            sa.String(length=50),
            nullable=False,
            comment="учётный номер квартала ФГИС ЛК",
        ),
        sa.Column("subject", sa.String(length=3), nullable=False, comment="субъект"),
        sa.Column(
            "subforestry",
            sa.String(length=10),
            nullable=True,
            comment="участковое лесничество",
        ),
        sa.Column(
            "quarter",
            sa.String(length=10),
            nullable=True,
            comment="номер квартала",
        ),
        sa.Column(
            "tract",
            sa.String(length=150),
            nullable=True,
            comment="урочище",
        ),
        sa.Column("status", sa.String(length=10), nullable=True, comment="status"),
        sa.Column(
            "read_at",
            sa.Date(),
            nullable=True,
            comment="дата чтения из СПД",
        ),
        sa.Column(
            "actuality_date",
            sa.Date(),
            nullable=True,
            comment="дата актуальности (появление в ФГИС ЛК)",
        ),
        sa.Column(
            "semantic_id",
            sa.Integer(),
            nullable=True,
            comment="идентификатор семантики WFS (QUARTER.{id})",
        ),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(geometry_type="GEOMETRY", spatial_index=False),
            nullable=True,
            comment="контур",
        ),
        sa.PrimaryKeyConstraint("subject", "fgis_id", name="quarters_pkey"),
        comment="квартал",
    )
    op.create_index("ix_quarters_fgis_id", "quarters", ["fgis_id"])
    op.create_index("ix_quarters_subject", "quarters", ["subject"])
    op.create_index(
        "ix_quarters_subject_read_at",
        "quarters",
        ["subject", "read_at"],
    )
    op.create_index(
        "ix_quarters_geom",
        "quarters",
        ["geom"],
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_index("ix_quarters_geom", table_name="quarters")
    op.drop_index("ix_quarters_subject_read_at", table_name="quarters")
    op.drop_index("ix_quarters_subject", table_name="quarters")
    op.drop_index("ix_quarters_fgis_id", table_name="quarters")
    op.drop_table("quarters")
