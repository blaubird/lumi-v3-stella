"""Canonical initial schema.

Revision ID: 001_initial_schema
Revises:
Create Date: 2025-05-31 12:57:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "public"


def _ensure_postgres_enum(dialect: str, name: str, values: list[str]) -> None:
    if dialect != "postgresql":
        return

    quoted_values = ", ".join(f"'{value}'" for value in values)
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_namespace n ON n.oid = t.typnamespace
                    WHERE t.typname = '{name}' AND n.nspname = '{SCHEMA}'
                ) THEN
                    CREATE TYPE {SCHEMA}.{name} AS ENUM ({quoted_values});
                END IF;
            END
            $$;
            """
        )
    )


def upgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    if dialect == "postgresql":
        op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))

    _ensure_postgres_enum(dialect, "role_enum", ["inbound", "assistant"])
    _ensure_postgres_enum(dialect, "direction_enum", ["inbound", "outbound"])
    _ensure_postgres_enum(
        dialect,
        "appt_status_enum",
        ["pending", "confirmed", "cancelled"],
    )

    role_enum_kwargs = {"name": "role_enum"}
    appt_status_kwargs = {"name": "appt_status_enum"}
    if dialect == "postgresql":
        role_enum_kwargs.update({"schema": SCHEMA, "create_type": False})
        appt_status_kwargs.update({"schema": SCHEMA, "create_type": False})

    role_enum = sa.Enum("inbound", "assistant", **role_enum_kwargs)
    appt_status_enum = sa.Enum(
        "pending", "confirmed", "cancelled", **appt_status_kwargs
    )

    op.create_table(
        "tenants",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("phone_id", sa.String(length=255), nullable=False),
        sa.Column("wh_token", sa.Text(), nullable=False),
        sa.Column(
            "system_prompt",
            sa.Text(),
            server_default="You are a helpful assistant.",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_tenants_id"),
        "tenants",
        ["id"],
        unique=False,
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_tenants_phone_id"),
        "tenants",
        ["phone_id"],
        unique=True,
        schema=SCHEMA,
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("wa_msg_id", sa.String(length=255), nullable=True),
        sa.Column("role", role_enum, nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=True),
        sa.Column(
            "ts",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            [f"{SCHEMA}.tenants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("wa_msg_id", name="uq_messages_wa_msg_id"),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_messages_tenant_id"),
        "messages",
        ["tenant_id"],
        unique=False,
        schema=SCHEMA,
    )

    op.create_table(
        "faqs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("question", sa.String(length=512), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            [f"{SCHEMA}.tenants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_faqs_tenant_id"),
        "faqs",
        ["tenant_id"],
        unique=False,
        schema=SCHEMA,
    )

    op.create_table(
        "usage",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("direction", sa.String(length=64), nullable=True),
        sa.Column(
            "msg_ts",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("tokens", sa.Integer(), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column(
            "prompt_tokens",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "completion_tokens",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_tokens",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("trace_id", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            [f"{SCHEMA}.tenants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_usage_tenant_id"),
        "usage",
        ["tenant_id"],
        unique=False,
        schema=SCHEMA,
    )
    op.create_index(
        "ix_usage_tenant_id_msg_ts",
        "usage",
        ["tenant_id", "msg_ts"],
        unique=False,
        schema=SCHEMA,
    )
    op.create_index(
        "ix_usage_tenant_id_id",
        "usage",
        ["tenant_id", "id"],
        unique=False,
        schema=SCHEMA,
    )

    op.create_table(
        "appointments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("customer_phone", sa.String(length=255), nullable=False),
        sa.Column("customer_email", sa.String(length=255), nullable=True),
        sa.Column("starts_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("status", appt_status_enum, nullable=False, server_default="pending"),
        sa.Column("google_event_id", sa.String(length=255), nullable=True),
        sa.Column(
            "reminded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_ts",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            [f"{SCHEMA}.tenants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_appointments_tenant_id"),
        "appointments",
        ["tenant_id"],
        unique=False,
        schema=SCHEMA,
    )

    op.create_table(
        "owner_contacts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("phone_number", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column(
            "created_ts",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            [f"{SCHEMA}.tenants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_owner_contacts_tenant_id"),
        "owner_contacts",
        ["tenant_id"],
        unique=False,
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_owner_contacts_phone_number"),
        "owner_contacts",
        ["phone_number"],
        unique=False,
        schema=SCHEMA,
    )

    op.create_table(
        "unavailability",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("owner_phone", sa.String(length=64), nullable=False),
        sa.Column("starts_on", sa.DATE(), nullable=False),
        sa.Column("ends_on", sa.DATE(), nullable=False),
        sa.Column(
            "created_ts",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            [f"{SCHEMA}.tenants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_unavailability_tenant_id"),
        "unavailability",
        ["tenant_id"],
        unique=False,
        schema=SCHEMA,
    )
    op.create_index(
        "ix_unavailability_tenant_dates",
        "unavailability",
        ["tenant_id", "starts_on", "ends_on"],
        unique=False,
        schema=SCHEMA,
    )


def downgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    op.drop_index(
        "ix_unavailability_tenant_dates",
        table_name="unavailability",
        schema=SCHEMA,
    )
    op.drop_index(
        op.f("ix_unavailability_tenant_id"),
        table_name="unavailability",
        schema=SCHEMA,
    )
    op.drop_table("unavailability", schema=SCHEMA)

    op.drop_index(
        op.f("ix_owner_contacts_phone_number"),
        table_name="owner_contacts",
        schema=SCHEMA,
    )
    op.drop_index(
        op.f("ix_owner_contacts_tenant_id"),
        table_name="owner_contacts",
        schema=SCHEMA,
    )
    op.drop_table("owner_contacts", schema=SCHEMA)

    op.drop_index(
        op.f("ix_appointments_tenant_id"),
        table_name="appointments",
        schema=SCHEMA,
    )
    op.drop_table("appointments", schema=SCHEMA)

    op.drop_index("ix_usage_tenant_id_id", table_name="usage", schema=SCHEMA)
    op.drop_index("ix_usage_tenant_id_msg_ts", table_name="usage", schema=SCHEMA)
    op.drop_index(op.f("ix_usage_tenant_id"), table_name="usage", schema=SCHEMA)
    op.drop_table("usage", schema=SCHEMA)

    op.drop_index(op.f("ix_faqs_tenant_id"), table_name="faqs", schema=SCHEMA)
    op.drop_table("faqs", schema=SCHEMA)

    op.drop_index(op.f("ix_messages_tenant_id"), table_name="messages", schema=SCHEMA)
    op.drop_table("messages", schema=SCHEMA)

    op.drop_index(op.f("ix_tenants_phone_id"), table_name="tenants", schema=SCHEMA)
    op.drop_index(op.f("ix_tenants_id"), table_name="tenants", schema=SCHEMA)
    op.drop_table("tenants", schema=SCHEMA)

    if dialect == "postgresql":
        op.execute(sa.text(f"DROP TYPE IF EXISTS {SCHEMA}.appt_status_enum"))
        op.execute(sa.text(f"DROP TYPE IF EXISTS {SCHEMA}.direction_enum"))
        op.execute(sa.text(f"DROP TYPE IF EXISTS {SCHEMA}.role_enum"))
        op.execute(sa.text("DROP EXTENSION IF EXISTS vector"))
