"""PostGIS.

Revision ID: 0001_postgis
Revises:
Create Date: 2026-08-30
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0001_postgis"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS postgis")
