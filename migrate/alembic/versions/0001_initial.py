"""базовая схема (PostGIS + слои + журнал).

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-04
"""

from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
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
        sa.Column("read_at", sa.Date(), nullable=True, comment="дата чтения из СПД"),
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
            comment="идентификатор семантики WFS (TAXATION_PIECE.{id})",
        ),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(geometry_type="GEOMETRY", spatial_index=False),
            nullable=True,
            comment="контур",
        ),
        sa.Column(
            "crs",
            sa.String(length=50),
            nullable=True,
            comment="система координат СПД",
        ),
        sa.PrimaryKeyConstraint("fgis_id", name="taxation_piece_pkey"),
        comment="выдел",
    )
    op.create_index("ix_taxation_piece_subject", "taxation_piece", ["subject"])
    op.create_index(
        "ix_taxation_piece_subject_read_at",
        "taxation_piece",
        ["subject", "read_at"],
    )
    op.create_index(
        "ix_taxation_piece_geom",
        "taxation_piece",
        ["geom"],
        postgresql_using="gist",
    )
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
        sa.Column("read_at", sa.Date(), nullable=True, comment="дата чтения из СПД"),
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
        sa.Column(
            "crs",
            sa.String(length=50),
            nullable=True,
            comment="система координат СПД",
        ),
        sa.Column(
            "clearcut_polled_at",
            sa.Date(),
            nullable=True,
            comment="дата опроса лесосек",
        ),
        sa.Column(
            "has_clearcuts",
            sa.Boolean(),
            nullable=True,
            comment="есть лесосеки",
        ),
        sa.PrimaryKeyConstraint("fgis_id", name="quarters_pkey"),
        comment="квартал",
    )
    op.create_index("ix_quarters_subject", "quarters", ["subject"])
    op.create_index("ix_quarters_subject_read_at", "quarters", ["subject", "read_at"])
    op.create_index(
        "ix_quarters_subject_clearcut_polled_at",
        "quarters",
        ["subject", "clearcut_polled_at"],
    )
    op.create_index("ix_quarters_geom", "quarters", ["geom"], postgresql_using="gist")
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
        sa.Column("read_at", sa.Date(), nullable=True, comment="дата чтения из СПД"),
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
            "crs",
            sa.String(length=50),
            nullable=True,
            comment="система координат СПД",
        ),
        sa.Column("limitation_dt", sa.Date(), nullable=True, comment="дата отвода"),
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
        sa.PrimaryKeyConstraint("fgis_id", name="clearcut_pkey"),
        comment="лесосека",
    )
    op.create_index("ix_clearcut_subject", "clearcut", ["subject"])
    op.create_index("ix_clearcut_subject_read_at", "clearcut", ["subject", "read_at"])
    op.create_index("ix_clearcut_geom", "clearcut", ["geom"], postgresql_using="gist")
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
        sa.Column("period_start", sa.Date(), nullable=True, comment="начало окна СПД"),
        sa.Column("period_end", sa.Date(), nullable=True, comment="конец окна СПД"),
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
    op.drop_index("ix_clearcut_geom", table_name="clearcut")
    op.drop_index("ix_clearcut_subject_read_at", table_name="clearcut")
    op.drop_index("ix_clearcut_subject", table_name="clearcut")
    op.drop_table("clearcut")
    op.drop_index("ix_quarters_geom", table_name="quarters")
    op.drop_index("ix_quarters_subject_clearcut_polled_at", table_name="quarters")
    op.drop_index("ix_quarters_subject_read_at", table_name="quarters")
    op.drop_index("ix_quarters_subject", table_name="quarters")
    op.drop_table("quarters")
    op.drop_index("ix_taxation_piece_geom", table_name="taxation_piece")
    op.drop_index("ix_taxation_piece_subject_read_at", table_name="taxation_piece")
    op.drop_index("ix_taxation_piece_subject", table_name="taxation_piece")
    op.drop_table("taxation_piece")
    op.execute("DROP EXTENSION IF EXISTS postgis")
