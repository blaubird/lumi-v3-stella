"""Squashed baseline for dev reset."""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

from logging_utils import get_logger

revision = "001_initial_squashed"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "public"
VECTOR_EXTENSION = "vector"
BTREE_GIST_EXTENSION = "btree_gist"
UNAVAILABILITY_EXCLUSION = "uq_unavailability_owner_dates"

logger = get_logger("alembic.001_initial_squashed")


def _ensure_extension(extension: str) -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect != "postgresql":
        logger.info(
            "Skipping extension on non-PostgreSQL dialect",
            extra={"extension": extension, "dialect": dialect},
        )
        return

    logger.info("Ensuring extension exists", extra={"extension": extension})
    op.execute(sa.text(f'CREATE EXTENSION IF NOT EXISTS "{extension}"'))


def _ensure_enum(name: str, values: Sequence[str]) -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect != "postgresql":
        logger.info(
            "Skipping enum creation on non-PostgreSQL dialect",
            extra={"enum": name, "dialect": dialect},
        )
        return

    quoted_values = ", ".join(f"'{value}'" for value in values)
    logger.info("Ensuring enum exists", extra={"enum": name})
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
            END;
            $$;
            """
        )
    )


def _build_enum(name: str, values: Sequence[str]) -> sa.Enum:
    bind = op.get_bind()
    enum_kwargs: dict[str, object] = {"name": name}
    if bind.dialect.name == "postgresql":
        _ensure_enum(name, values)
        enum_kwargs.update({"schema": SCHEMA, "create_type": False})
    return sa.Enum(*values, **enum_kwargs)


def _table_exists(bind: sa.engine.Connection, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return inspector.has_table(table_name, schema=SCHEMA)


def _index_exists(bind: sa.engine.Connection, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    indexes = inspector.get_indexes(table_name, schema=SCHEMA)
    return any(idx["name"] == index_name for idx in indexes)


def _constraint_exists(bind: sa.engine.Connection, constraint_name: str) -> bool:
    if bind.dialect.name != "postgresql":
        return False
    result = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_constraint c
            JOIN pg_namespace n ON n.oid = c.connamespace
            WHERE c.conname = :constraint_name AND n.nspname = :schema_name
            """
        ),
        {"constraint_name": constraint_name, "schema_name": SCHEMA},
    )
    return result.scalar() is not None


def _create_index_if_missing(
    bind: sa.engine.Connection,
    index_name: str,
    table_name: str,
    columns: Sequence[str],
    *,
    unique: bool = False,
) -> None:
    if _index_exists(bind, table_name, index_name):
        logger.info(
            "Index already exists; skipping create",
            extra={"table": f"{SCHEMA}.{table_name}", "index": index_name},
        )
        return

    logger.info(
        "Creating index",
        extra={"table": f"{SCHEMA}.{table_name}", "index": index_name},
    )
    op.create_index(index_name, table_name, list(columns), unique=unique, schema=SCHEMA)


def _drop_index_if_exists(
    bind: sa.engine.Connection,
    index_name: str,
    table_name: str,
) -> None:
    if not _table_exists(bind, table_name):
        logger.info(
            "Skipping drop index; table missing",
            extra={"table": f"{SCHEMA}.{table_name}", "index": index_name},
        )
        return
    if not _index_exists(bind, table_name, index_name):
        logger.info(
            "Skipping drop index; index missing",
            extra={"table": f"{SCHEMA}.{table_name}", "index": index_name},
        )
        return

    logger.info(
        "Dropping index",
        extra={"table": f"{SCHEMA}.{table_name}", "index": index_name},
    )
    op.drop_index(index_name, table_name=table_name, schema=SCHEMA)


def _drop_table_if_exists(bind: sa.engine.Connection, table_name: str) -> None:
    if not _table_exists(bind, table_name):
        logger.info(
            "Skipping drop table; already absent",
            extra={"table": f"{SCHEMA}.{table_name}"},
        )
        return

    logger.info("Dropping table", extra={"table": f"{SCHEMA}.{table_name}"})
    op.drop_table(table_name, schema=SCHEMA)


def _ensure_unavailability_constraint(bind: sa.engine.Connection) -> None:
    if bind.dialect.name != "postgresql":
        logger.info(
            "Skipping exclusion constraint on non-PostgreSQL dialect",
            extra={"constraint": UNAVAILABILITY_EXCLUSION},
        )
        return

    if _constraint_exists(bind, UNAVAILABILITY_EXCLUSION):
        logger.info(
            "Exclusion constraint already exists; skipping create",
            extra={"constraint": UNAVAILABILITY_EXCLUSION},
        )
        return

    logger.info(
        "Creating exclusion constraint",
        extra={"constraint": UNAVAILABILITY_EXCLUSION},
    )
    op.execute(
        sa.text(
            f"""
            ALTER TABLE "{SCHEMA}"."unavailability"
            ADD CONSTRAINT {UNAVAILABILITY_EXCLUSION}
            EXCLUDE USING gist (
                tenant_id WITH =,
                owner_phone WITH =,
                daterange(starts_on, ends_on, '[]') WITH &&
            )
            """
        )
    )


def _drop_unavailability_constraint(bind: sa.engine.Connection) -> None:
    if bind.dialect.name != "postgresql":
        return
    if not _constraint_exists(bind, UNAVAILABILITY_EXCLUSION):
        logger.info(
            "Skipping drop constraint; already absent",
            extra={"constraint": UNAVAILABILITY_EXCLUSION},
        )
        return

    logger.info(
        "Dropping exclusion constraint",
        extra={"constraint": UNAVAILABILITY_EXCLUSION},
    )
    op.execute(
        sa.text(
            f"""
            ALTER TABLE "{SCHEMA}"."unavailability"
            DROP CONSTRAINT {UNAVAILABILITY_EXCLUSION}
            """
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    logger.info("Starting baseline upgrade", extra={"schema": SCHEMA})

    _ensure_extension(VECTOR_EXTENSION)
    _ensure_extension(BTREE_GIST_EXTENSION)

    role_enum = _build_enum("role_enum", ["inbound", "assistant"])
    appt_status_enum = _build_enum(
        "appt_status_enum", ["pending", "confirmed", "cancelled"]
    )

    if not _table_exists(bind, "tenants"):
        logger.info("Creating table", extra={"table": f"{SCHEMA}.tenants"})
        op.create_table(
            "tenants",
            sa.Column("id", sa.String(length=255), nullable=False),
            sa.Column("phone_id", sa.String(length=255), nullable=False),
            sa.Column("wh_token", sa.Text(), nullable=False),
            sa.Column(
                "system_prompt",
                sa.Text(),
                nullable=False,
                server_default="You are a helpful assistant.",
            ),
            sa.PrimaryKeyConstraint("id"),
            schema=SCHEMA,
        )
    else:
        logger.info(
            "Table already exists; skipping create",
            extra={"table": f"{SCHEMA}.tenants"},
        )

    _create_index_if_missing(bind, op.f("ix_tenants_id"), "tenants", ["id"])
    _create_index_if_missing(
        bind,
        "uq_tenants_phone_id",
        "tenants",
        ["phone_id"],
        unique=True,
    )

    if not _table_exists(bind, "messages"):
        logger.info("Creating table", extra={"table": f"{SCHEMA}.messages"})
        op.create_table(
            "messages",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.String(length=255), nullable=False),
            sa.Column("wa_msg_id", sa.String(length=255), nullable=True),
            sa.Column("role", role_enum, nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("tokens", sa.Integer(), nullable=True),
            sa.Column(
                "ts",
                sa.TIMESTAMP(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"], [f"{SCHEMA}.tenants.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("wa_msg_id", name="uq_messages_wa_msg_id"),
            schema=SCHEMA,
        )
    else:
        logger.info(
            "Table already exists; skipping create",
            extra={"table": f"{SCHEMA}.messages"},
        )

    _create_index_if_missing(bind, op.f("ix_messages_tenant_id"), "messages", ["tenant_id"])

    if not _table_exists(bind, "faqs"):
        logger.info("Creating table", extra={"table": f"{SCHEMA}.faqs"})
        op.create_table(
            "faqs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.String(length=255), nullable=False),
            sa.Column("question", sa.String(length=500), nullable=False),
            sa.Column("answer", sa.Text(), nullable=False),
            sa.Column("embedding", Vector(1536), nullable=True),
            sa.ForeignKeyConstraint(
                ["tenant_id"], [f"{SCHEMA}.tenants.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
            schema=SCHEMA,
        )
    else:
        logger.info(
            "Table already exists; skipping create",
            extra={"table": f"{SCHEMA}.faqs"},
        )

    _create_index_if_missing(bind, op.f("ix_faqs_tenant_id"), "faqs", ["tenant_id"])

    if not _table_exists(bind, "usage"):
        logger.info("Creating table", extra={"table": f"{SCHEMA}.usage"})
        op.create_table(
            "usage",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.String(length=255), nullable=False),
            sa.Column("direction", sa.String(length=64), nullable=True),
            sa.Column("tokens", sa.Integer(), nullable=True),
            sa.Column(
                "msg_ts",
                sa.TIMESTAMP(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("model", sa.String(length=255), nullable=True),
            sa.Column(
                "prompt_tokens",
                sa.Integer(),
                nullable=False,
                default=0,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "completion_tokens",
                sa.Integer(),
                nullable=False,
                default=0,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "total_tokens",
                sa.Integer(),
                nullable=False,
                default=0,
                server_default=sa.text("0"),
            ),
            sa.Column("trace_id", sa.String(length=255), nullable=True),
            sa.ForeignKeyConstraint(
                ["tenant_id"], [f"{SCHEMA}.tenants.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
            schema=SCHEMA,
        )
    else:
        logger.info(
            "Table already exists; skipping create",
            extra={"table": f"{SCHEMA}.usage"},
        )

    _create_index_if_missing(bind, op.f("ix_usage_tenant_id"), "usage", ["tenant_id"])
    _create_index_if_missing(
        bind,
        "ix_usage_tenant_id_msg_ts",
        "usage",
        ["tenant_id", "msg_ts"],
    )
    _create_index_if_missing(
        bind,
        "ix_usage_tenant_id_id",
        "usage",
        ["tenant_id", "id"],
    )

    if not _table_exists(bind, "appointments"):
        logger.info("Creating table", extra={"table": f"{SCHEMA}.appointments"})
        op.create_table(
            "appointments",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.String(length=255), nullable=False),
            sa.Column("customer_phone", sa.String(length=50), nullable=False),
            sa.Column("customer_email", sa.String(length=255), nullable=True),
            sa.Column("starts_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.Column(
                "status",
                appt_status_enum,
                nullable=False,
                server_default=sa.text("'pending'"),
            ),
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
                ["tenant_id"], [f"{SCHEMA}.tenants.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
            schema=SCHEMA,
        )
    else:
        logger.info(
            "Table already exists; skipping create",
            extra={"table": f"{SCHEMA}.appointments"},
        )

    _create_index_if_missing(bind, op.f("ix_appointments_tenant_id"), "appointments", ["tenant_id"])

    if not _table_exists(bind, "owner_contacts"):
        logger.info("Creating table", extra={"table": f"{SCHEMA}.owner_contacts"})
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
                ["tenant_id"], [f"{SCHEMA}.tenants.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
            schema=SCHEMA,
        )
    else:
        logger.info(
            "Table already exists; skipping create",
            extra={"table": f"{SCHEMA}.owner_contacts"},
        )

    _create_index_if_missing(
        bind,
        op.f("ix_owner_contacts_tenant_id"),
        "owner_contacts",
        ["tenant_id"],
    )
    _create_index_if_missing(
        bind,
        op.f("ix_owner_contacts_phone_number"),
        "owner_contacts",
        ["phone_number"],
    )

    if not _table_exists(bind, "unavailability"):
        logger.info("Creating table", extra={"table": f"{SCHEMA}.unavailability"})
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
                ["tenant_id"], [f"{SCHEMA}.tenants.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
            schema=SCHEMA,
        )
    else:
        logger.info(
            "Table already exists; skipping create",
            extra={"table": f"{SCHEMA}.unavailability"},
        )

    _create_index_if_missing(
        bind,
        op.f("ix_unavailability_tenant_id"),
        "unavailability",
        ["tenant_id"],
    )
    _create_index_if_missing(
        bind,
        "ix_unavailability_tenant_dates",
        "unavailability",
        ["tenant_id", "starts_on", "ends_on"],
    )

    _ensure_unavailability_constraint(bind)

    logger.info("Baseline upgrade complete", extra={"schema": SCHEMA})


def downgrade() -> None:
    bind = op.get_bind()
    logger.info("Starting baseline downgrade", extra={"schema": SCHEMA})

    _drop_unavailability_constraint(bind)

    _drop_index_if_exists(bind, "ix_unavailability_tenant_dates", "unavailability")
    _drop_index_if_exists(bind, op.f("ix_unavailability_tenant_id"), "unavailability")
    _drop_table_if_exists(bind, "unavailability")

    _drop_index_if_exists(bind, op.f("ix_owner_contacts_phone_number"), "owner_contacts")
    _drop_index_if_exists(bind, op.f("ix_owner_contacts_tenant_id"), "owner_contacts")
    _drop_table_if_exists(bind, "owner_contacts")

    _drop_index_if_exists(bind, op.f("ix_appointments_tenant_id"), "appointments")
    _drop_table_if_exists(bind, "appointments")

    _drop_index_if_exists(bind, "ix_usage_tenant_id_id", "usage")
    _drop_index_if_exists(bind, "ix_usage_tenant_id_msg_ts", "usage")
    _drop_index_if_exists(bind, op.f("ix_usage_tenant_id"), "usage")
    _drop_table_if_exists(bind, "usage")

    _drop_index_if_exists(bind, op.f("ix_faqs_tenant_id"), "faqs")
    _drop_table_if_exists(bind, "faqs")

    _drop_index_if_exists(bind, op.f("ix_messages_tenant_id"), "messages")
    _drop_table_if_exists(bind, "messages")

    _drop_index_if_exists(bind, "uq_tenants_phone_id", "tenants")
    _drop_index_if_exists(bind, op.f("ix_tenants_id"), "tenants")
    _drop_table_if_exists(bind, "tenants")

    if bind.dialect.name == "postgresql":
        logger.info("Dropping enums and extensions", extra={"schema": SCHEMA})
        op.execute(sa.text(f'DROP TYPE IF EXISTS "{SCHEMA}"."appt_status_enum"'))
        op.execute(sa.text(f'DROP TYPE IF EXISTS "{SCHEMA}"."role_enum"'))
        op.execute(sa.text(f'DROP EXTENSION IF EXISTS "{VECTOR_EXTENSION}"'))
        op.execute(sa.text(f'DROP EXTENSION IF EXISTS "{BTREE_GIST_EXTENSION}"'))

    logger.info("Baseline downgrade complete", extra={"schema": SCHEMA})
