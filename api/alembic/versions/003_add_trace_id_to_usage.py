"""Ensure trace_id column exists on usage.

Revision ID: 003_add_trace_id_to_usage
Revises: 002_usage_alignment
Create Date: 2025-11-18 09:00:00.000000
"""

from __future__ import annotations

from typing import Final

import sqlalchemy as sa
from alembic import op

revision = "003_add_trace_id_to_usage"
down_revision = "002_usage_alignment"
branch_labels = None
depends_on = None

SCHEMA: Final[str] = "public"
TABLE_NAME: Final[str] = "usage"
COLUMN_NAME: Final[str] = "trace_id"
TRACE_ID_COLUMN = sa.Column(COLUMN_NAME, sa.String(length=255), nullable=True)


def _table_exists(inspector: sa.Inspector) -> bool:
    return inspector.has_table(TABLE_NAME, schema=SCHEMA)


def _current_columns(inspector: sa.Inspector) -> set[str]:
    return {
        column["name"]
        for column in inspector.get_columns(TABLE_NAME, schema=SCHEMA)
    }


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    if not _table_exists(inspector):
        return

    columns = _current_columns(inspector)
    if COLUMN_NAME not in columns:
        op.add_column(TABLE_NAME, TRACE_ID_COLUMN.copy(), schema=SCHEMA)


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    if not _table_exists(inspector):
        return

    columns = _current_columns(inspector)
    if COLUMN_NAME in columns:
        op.drop_column(TABLE_NAME, COLUMN_NAME, schema=SCHEMA)
