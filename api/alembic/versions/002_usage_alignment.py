"""Repair usage table shape without destructive changes.

Revision ID: 002_usage_alignment
Revises: 001_initial_schema
Create Date: 2024-06-05 12:00:00.000000
"""

from __future__ import annotations

from typing import Dict, Tuple

import sqlalchemy as sa
from alembic import op

revision = "002_usage_alignment"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None

SCHEMA = "public"

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

USAGE_INDEXES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (op.f("ix_usage_tenant_id"), ("tenant_id",)),
    ("ix_usage_tenant_id_msg_ts", ("tenant_id", "msg_ts")),
    ("ix_usage_tenant_id_id", ("tenant_id", "id")),
)


def _refresh_inspector(connection: sa.engine.Connection) -> sa.Inspector:
    return sa.inspect(connection)


def _qualified(table: str) -> str:
    return f"{SCHEMA}.{table}"


def upgrade() -> None:
    connection = op.get_bind()
    inspector = _refresh_inspector(connection)
    dialect = connection.dialect.name

    table_exists = inspector.has_table("usage", schema=SCHEMA)

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
            sa.ForeignKeyConstraint(
                ["tenant_id"], [f"{SCHEMA}.tenants.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
            schema=SCHEMA,
        )
    else:
        columns = {
            column["name"]: column
            for column in inspector.get_columns("usage", schema=SCHEMA)
        }

        def _add_column_if_missing(name: str) -> None:
            if name not in columns:
                op.add_column("usage", USAGE_COLUMNS[name].copy(), schema=SCHEMA)
                columns[name] = {
                    "name": name,
                    "type": USAGE_COLUMNS[name].type,
                    "nullable": USAGE_COLUMNS[name].nullable,
                }

        for column_name in ("model", "direction", "msg_ts"):
            _add_column_if_missing(column_name)

        for numeric_name in ("prompt_tokens", "completion_tokens", "total_tokens"):
            _add_column_if_missing(numeric_name)
            op.execute(
                sa.text(
                    f"UPDATE {_qualified('usage')} "
                    f"SET {numeric_name} = 0 "
                    f"WHERE {numeric_name} IS NULL"
                )
            )
            op.alter_column(
                "usage",
                numeric_name,
                existing_type=sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
                schema=SCHEMA,
            )

        if "tokens" in columns and columns["tokens"].get("nullable") is False:
            op.alter_column(
                "usage",
                "tokens",
                existing_type=sa.Integer(),
                nullable=True,
                schema=SCHEMA,
            )

        if "tenant_id" in columns:
            tenant_type = columns["tenant_id"]["type"]
            if getattr(tenant_type, "length", None) != 255:
                op.alter_column(
                    "usage",
                    "tenant_id",
                    existing_type=tenant_type,
                    type_=sa.String(length=255),
                    schema=SCHEMA,
                )
                tenant_type = sa.String(length=255)
            if columns["tenant_id"].get("nullable"):
                null_exists = connection.execute(
                    sa.text(
                        f"SELECT 1 FROM {_qualified('usage')} "
                        "WHERE tenant_id IS NULL LIMIT 1"
                    )
                ).fetchone()
                if null_exists is None:
                    op.alter_column(
                        "usage",
                        "tenant_id",
                        existing_type=tenant_type,
                        nullable=False,
                        schema=SCHEMA,
                    )

        if "direction" in columns:
            direction_type = columns["direction"]["type"]
            if isinstance(direction_type, sa.Enum):
                if dialect == "postgresql":
                    op.execute(
                        sa.text(
                            f"ALTER TABLE {_qualified('usage')} "
                            "ALTER COLUMN direction TYPE VARCHAR(64) "
                            "USING direction::text"
                        )
                    )
                else:
                    op.alter_column(
                        "usage",
                        "direction",
                        existing_type=direction_type,
                        type_=sa.String(length=64),
                        schema=SCHEMA,
                    )
                direction_type = sa.String(length=64)
            if getattr(direction_type, "length", 0) < 64:
                op.alter_column(
                    "usage",
                    "direction",
                    existing_type=direction_type,
                    type_=sa.String(length=64),
                    schema=SCHEMA,
                )
            op.alter_column(
                "usage",
                "direction",
                existing_type=sa.String(length=64),
                nullable=True,
                schema=SCHEMA,
            )

        if "msg_ts" in columns:
            msg_ts_type = columns["msg_ts"]["type"]
            if getattr(msg_ts_type, "timezone", False) is False:
                if dialect == "postgresql":
                    op.execute(
                        sa.text(
                            f"ALTER TABLE {_qualified('usage')} "
                            "ALTER COLUMN msg_ts TYPE TIMESTAMPTZ "
                            "USING timezone('UTC', msg_ts)"
                        )
                    )
                else:
                    op.alter_column(
                        "usage",
                        "msg_ts",
                        existing_type=msg_ts_type,
                        type_=sa.TIMESTAMP(timezone=True),
                        schema=SCHEMA,
                    )
            op.alter_column(
                "usage",
                "msg_ts",
                existing_type=sa.TIMESTAMP(timezone=True),
                server_default=sa.text("now()"),
                schema=SCHEMA,
            )
            if columns["msg_ts"].get("nullable"):
                null_exists = connection.execute(
                    sa.text(
                        f"SELECT 1 FROM {_qualified('usage')} "
                        "WHERE msg_ts IS NULL LIMIT 1"
                    )
                ).fetchone()
                if null_exists is None:
                    op.alter_column(
                        "usage",
                        "msg_ts",
                        existing_type=sa.TIMESTAMP(timezone=True),
                        nullable=False,
                        schema=SCHEMA,
                    )

        if "id" in columns and not isinstance(columns["id"]["type"], sa.BigInteger):
            op.alter_column(
                "usage",
                "id",
                existing_type=columns["id"]["type"],
                type_=sa.BigInteger(),
                nullable=False,
                autoincrement=True,
                schema=SCHEMA,
            )

    inspector = _refresh_inspector(connection)

    fk_constraints = inspector.get_foreign_keys("usage", schema=SCHEMA)
    has_usage_fk = any(
        fk["referred_table"] == "tenants"
        and fk.get("referred_schema", SCHEMA) == SCHEMA
        for fk in fk_constraints
    )
    if not has_usage_fk:
        op.create_foreign_key(
            "usage_tenant_id_fkey",
            "usage",
            "tenants",
            ["tenant_id"],
            ["id"],
            source_schema=SCHEMA,
            referent_schema=SCHEMA,
            ondelete="CASCADE",
        )

    inspector = _refresh_inspector(connection)
    existing_indexes = {
        index["name"] for index in inspector.get_indexes("usage", schema=SCHEMA)
    }

    for index_name, columns in USAGE_INDEXES:
        if index_name not in existing_indexes:
            op.create_index(index_name, "usage", list(columns), schema=SCHEMA)


def downgrade() -> None:
    connection = op.get_bind()
    inspector = _refresh_inspector(connection)

    if not inspector.has_table("usage", schema=SCHEMA):
        return

    # Canonical revision 001 already defines the full usage shape.
    # No-op downgrade keeps the schema aligned with that baseline.
    return
