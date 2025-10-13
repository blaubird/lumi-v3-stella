"""Align usage table with ORM expectations.

Revision ID: 002_usage_alignment
Revises: 001_initial_schema
Create Date: 2024-06-05 12:00:00.000000
"""

from __future__ import annotations

from typing import Dict

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision = "002_usage_alignment"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


USAGE_COLUMNS: Dict[str, sa.Column] = {
    "id": sa.Column(
        "id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False
    ),
    "tenant_id": sa.Column("tenant_id", sa.String(length=255), nullable=False),
    "direction": sa.Column("direction", sa.String(length=64), nullable=True),
    "msg_ts": sa.Column(
        "msg_ts",
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    "tokens": sa.Column("tokens", sa.Integer(), nullable=True),
    "model": sa.Column("model", sa.String(length=255), nullable=True),
    "prompt_tokens": sa.Column(
        "prompt_tokens",
        sa.Integer(),
        nullable=False,
        server_default=sa.text("0"),
    ),
    "completion_tokens": sa.Column(
        "completion_tokens",
        sa.Integer(),
        nullable=False,
        server_default=sa.text("0"),
    ),
    "total_tokens": sa.Column(
        "total_tokens",
        sa.Integer(),
        nullable=False,
        server_default=sa.text("0"),
    ),
    "trace_id": sa.Column("trace_id", sa.String(length=255), nullable=True),
}

USAGE_INDEXES = (
    ("ix_usage_tenant_id_msg_ts", ("tenant_id", "msg_ts")),
    ("ix_usage_tenant_id_id", ("tenant_id", "id")),
)


def _refresh_inspector(connection: sa.engine.Connection) -> sa.Inspector:
    return sa.inspect(connection)


def upgrade() -> None:
    connection = op.get_bind()
    inspector = _refresh_inspector(connection)

    table_exists = inspector.has_table("usage")

    if not table_exists:
        op.create_table(
            "usage",
            USAGE_COLUMNS["id"].copy(),
            USAGE_COLUMNS["tenant_id"].copy(),
            USAGE_COLUMNS["direction"].copy(),
            USAGE_COLUMNS["msg_ts"].copy(),
            USAGE_COLUMNS["tokens"].copy(),
            USAGE_COLUMNS["model"].copy(),
            USAGE_COLUMNS["prompt_tokens"].copy(),
            USAGE_COLUMNS["completion_tokens"].copy(),
            USAGE_COLUMNS["total_tokens"].copy(),
            USAGE_COLUMNS["trace_id"].copy(),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    else:
        columns = {column["name"]: column for column in inspector.get_columns("usage")}
        dialect = connection.dialect.name

        if "model" not in columns:
            op.add_column("usage", USAGE_COLUMNS["model"].copy())

        for numeric_column in ("prompt_tokens", "completion_tokens", "total_tokens"):
            if numeric_column not in columns:
                op.add_column("usage", USAGE_COLUMNS[numeric_column].copy())
                op.execute(
                    text(
                        f"UPDATE usage SET {numeric_column} = 0 WHERE {numeric_column} IS NULL"
                    )
                )
            else:
                if columns[numeric_column]["nullable"]:
                    op.execute(
                        text(
                            f"UPDATE usage SET {numeric_column} = 0 WHERE {numeric_column} IS NULL"
                        )
                    )
                op.alter_column(
                    "usage",
                    numeric_column,
                    existing_type=sa.Integer(),
                    nullable=False,
                    server_default=sa.text("0"),
                )

        if "tokens" in columns and not columns["tokens"]["nullable"]:
            op.alter_column(
                "usage",
                "tokens",
                existing_type=sa.Integer(),
                nullable=True,
            )

        if "direction" in columns:
            column_type = columns["direction"]["type"]
            if isinstance(column_type, sa.Enum):
                if dialect == "postgresql":
                    op.execute(
                        "ALTER TABLE usage ALTER COLUMN direction TYPE VARCHAR(64) "
                        "USING direction::text"
                    )
                else:
                    op.alter_column(
                        "usage",
                        "direction",
                        type_=sa.String(length=64),
                        existing_type=column_type,
                    )
                op.alter_column(
                    "usage",
                    "direction",
                    existing_type=sa.String(length=64),
                    nullable=True,
                )
            else:
                if (
                    getattr(column_type, "length", None) is None
                    or column_type.length < 64
                ):
                    op.alter_column(
                        "usage",
                        "direction",
                        existing_type=column_type,
                        type_=sa.String(length=64),
                    )
                if not columns["direction"]["nullable"]:
                    op.alter_column(
                        "usage",
                        "direction",
                        existing_type=sa.String(length=64),
                        nullable=True,
                    )
        else:
            op.add_column("usage", USAGE_COLUMNS["direction"].copy())

        if "msg_ts" in columns:
            op.alter_column(
                "usage",
                "msg_ts",
                existing_type=sa.TIMESTAMP(timezone=True),
                server_default=sa.text("now()"),
            )
        else:
            op.add_column("usage", USAGE_COLUMNS["msg_ts"].copy())

        if "id" in columns and not isinstance(columns["id"]["type"], sa.BigInteger):
            op.alter_column(
                "usage",
                "id",
                existing_type=columns["id"]["type"],
                type_=sa.BigInteger(),
                nullable=False,
                autoincrement=True,
            )

        if "tenant_id" in columns:
            current_type = columns["tenant_id"]["type"]
            if getattr(current_type, "length", None) != 255:
                op.alter_column(
                    "usage",
                    "tenant_id",
                    existing_type=current_type,
                    type_=sa.String(length=255),
                )

    inspector = _refresh_inspector(connection)
    existing_indexes = {index["name"] for index in inspector.get_indexes("usage")}

    for index_name, columns in USAGE_INDEXES:
        if index_name not in existing_indexes:
            op.create_index(index_name, "usage", list(columns))


def downgrade() -> None:
    connection = op.get_bind()
    inspector = _refresh_inspector(connection)

    if not inspector.has_table("usage"):
        return

    existing_indexes = {index["name"] for index in inspector.get_indexes("usage")}
    for index_name, _columns in USAGE_INDEXES:
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name="usage")

    columns = {column["name"]: column for column in inspector.get_columns("usage")}

    for numeric_column in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if numeric_column in columns:
            op.alter_column(
                "usage",
                numeric_column,
                existing_type=sa.Integer(),
                nullable=True,
                server_default=sa.text("0"),
            )

    if "tokens" in columns:
        op.alter_column(
            "usage",
            "tokens",
            existing_type=sa.Integer(),
            nullable=False,
        )

    dialect = connection.dialect.name
    if "direction" in columns:
        if dialect == "postgresql":
            op.execute(
                "ALTER TABLE usage ALTER COLUMN direction TYPE direction_enum "
                "USING direction::direction_enum"
            )
            enum_type = sa.Enum("inbound", "outbound", name="direction_enum")
        else:
            enum_type = sa.Enum("inbound", "outbound", name="direction_enum")
        op.alter_column(
            "usage",
            "direction",
            existing_type=enum_type,
            nullable=False,
        )

    if "msg_ts" in columns:
        op.alter_column(
            "usage",
            "msg_ts",
            existing_type=sa.TIMESTAMP(timezone=True),
            server_default=None,
        )

    if "id" in columns and isinstance(columns["id"]["type"], sa.BigInteger):
        op.alter_column(
            "usage",
            "id",
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            nullable=False,
            autoincrement=True,
        )

    if "tenant_id" in columns:
        current_type = columns["tenant_id"]["type"]
        if getattr(current_type, "length", None) == 255:
            op.alter_column(
                "usage",
                "tenant_id",
                existing_type=current_type,
                type_=sa.String(),
            )

    if "model" in columns and columns["model"]["default"] is None:
        # Column existed prior to this revision in canonical history; leave as-is.
        pass
