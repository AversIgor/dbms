"""лесосека (clearcut).

Revision ID: 0009_clearcut
Revises: 0008_quarters
Create Date: 2026-09-03
"""

from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "0009_clearcut"
down_revision: Union[str, Sequence[str], None] = "0008_quarters"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "clearcut",
        sa.Column(
            "fgis_id",
            sa.String(length=50),
            nullable=False,
            comment="учётный номер лесосеки ФГИС ЛК",
        ),
        sa.Column("subject", sa.String(length=3), nullable=False, comment="субъект"),
        sa.Column(
            "quarter",
            sa.String(length=20),
            nullable=True,
            comment="номер квартала",
        ),
        sa.Column(
            "area",
            sa.Numeric(precision=16, scale=5),
            nullable=True,
            comment="площадь",
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
            comment="идентификатор семантики WFS (CLEARCUT.{id})",
        ),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(geometry_type="GEOMETRY", spatial_index=False),
            nullable=True,
            comment="контур",
        ),
        sa.Column(
            "limitation_dt",
            sa.String(length=20),
            nullable=True,
            comment="дата отвода",
        ),
        sa.Column(
            "clearcut_no",
            sa.String(length=50),
            nullable=True,
            comment="номер лесосеки",
        ),
        sa.Column(
            "basis_doc_no",
            sa.String(length=50),
            nullable=True,
            comment="номер документа-основания",
        ),
        sa.PrimaryKeyConstraint("subject", "fgis_id", name="clearcut_pkey"),
        comment="лесосека",
    )
    op.create_index("ix_clearcut_fgis_id", "clearcut", ["fgis_id"])
    op.create_index("ix_clearcut_subject", "clearcut", ["subject"])
    op.create_index(
        "ix_clearcut_subject_read_at",
        "clearcut",
        ["subject", "read_at"],
    )
    op.create_index(
        "ix_clearcut_geom",
        "clearcut",
        ["geom"],
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_index("ix_clearcut_geom", table_name="clearcut")
    op.drop_index("ix_clearcut_subject_read_at", table_name="clearcut")
    op.drop_index("ix_clearcut_subject", table_name="clearcut")
    op.drop_index("ix_clearcut_fgis_id", table_name="clearcut")
    op.drop_table("clearcut")
