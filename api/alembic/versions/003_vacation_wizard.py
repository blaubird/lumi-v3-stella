"""Add owner contacts and unavailability tables for vacation wizard."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection, Inspector

revision = "003_vacation_wizard"
down_revision = "002_usage_alignment"
branch_labels = None
depends_on = None

SCHEMA = "public"

OWNER_TABLE = "owner_contacts"
UNAVAIL_TABLE = "unavailability"

IDX_OWNER_TENANT = op.f("ix_owner_contacts_tenant_id")
IDX_OWNER_PHONE = op.f("ix_owner_contacts_phone_number")
IDX_UNAVAIL_TENANT = op.f("ix_unavailability_tenant_id")
IDX_UNAVAIL_DATES = "ix_unavailability_tenant_dates"
EXCL_UNAVAILABILITY = "uq_unavailability_owner_dates"
BTREE_GIST_EXTENSION = "btree_gist"


OWNER_COLUMNS = [
    sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
    sa.Column("tenant_id", sa.String(length=255), nullable=False),
    sa.Column("phone_number", sa.String(length=64), nullable=False),
    sa.Column("display_name", sa.String(length=255), nullable=True),
    sa.Column(
        "created_ts",
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    ),
    sa.ForeignKeyConstraint(["tenant_id"], [f"{SCHEMA}.tenants.id"], ondelete="CASCADE"),
]

UNAVAIL_COLUMNS = [
    sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
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
    sa.ForeignKeyConstraint(["tenant_id"], [f"{SCHEMA}.tenants.id"], ondelete="CASCADE"),
]


def _create_table_if_missing(
    inspector: Inspector,
    table_name: str,
    columns: list[sa.Column],
) -> None:
    if inspector.has_table(table_name, schema=SCHEMA):
        return

    op.create_table(table_name, *[column.copy() for column in columns], schema=SCHEMA)


def _ensure_index(
    inspector: Inspector,
    table_name: str,
    index_name: str,
    columns: tuple[str, ...],
    *,
    unique: bool = False,
) -> None:
    existing = {
        index["name"]
        for index in inspector.get_indexes(table_name, schema=SCHEMA)
    }
    if index_name in existing:
        return

    op.create_index(index_name, table_name, columns, unique=unique, schema=SCHEMA)


def _ensure_extension(connection: Connection, extension_name: str) -> None:
    if connection.dialect.name != "postgresql":
        return

    op.execute(sa.text(f"CREATE EXTENSION IF NOT EXISTS {extension_name}"))


def _ensure_exclusion_constraint(
    connection: Connection,
    table_name: str,
    constraint_name: str,
) -> None:
    if connection.dialect.name != "postgresql":
        return

    exists = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = :schema
              AND t.relname = :table
              AND c.conname = :constraint
            LIMIT 1
            """
        ),
        {"schema": SCHEMA, "table": table_name, "constraint": constraint_name},
    ).scalar()

    if exists:
        return

    qualified_table = f'"{SCHEMA}"."{table_name}"'
    op.execute(
        sa.text(
            """
            ALTER TABLE {qualified_table}
            ADD CONSTRAINT {constraint_name}
            EXCLUDE USING gist (
                tenant_id WITH =,
                owner_phone WITH =,
                daterange(starts_on, ends_on, '[]') WITH &&
            )
            """.format(
                qualified_table=qualified_table, constraint_name=constraint_name
            )
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    _create_table_if_missing(inspector, OWNER_TABLE, OWNER_COLUMNS)
    inspector = sa.inspect(bind)
    _ensure_index(inspector, OWNER_TABLE, IDX_OWNER_TENANT, ("tenant_id",))
    _ensure_index(inspector, OWNER_TABLE, IDX_OWNER_PHONE, ("phone_number",))

    inspector = sa.inspect(bind)
    _create_table_if_missing(inspector, UNAVAIL_TABLE, UNAVAIL_COLUMNS)
    inspector = sa.inspect(bind)
    _ensure_index(inspector, UNAVAIL_TABLE, IDX_UNAVAIL_TENANT, ("tenant_id",))
    _ensure_index(
        inspector,
        UNAVAIL_TABLE,
        IDX_UNAVAIL_DATES,
        ("tenant_id", "starts_on", "ends_on"),
    )

    _ensure_extension(bind, BTREE_GIST_EXTENSION)
    _ensure_exclusion_constraint(bind, UNAVAIL_TABLE, EXCL_UNAVAILABILITY)


def _drop_index_if_exists(
    inspector: Inspector,
    table_name: str,
    index_name: str,
) -> None:
    existing = {
        index["name"]
        for index in inspector.get_indexes(table_name, schema=SCHEMA)
    }
    if index_name not in existing:
        return

    op.drop_index(index_name, table_name=table_name, schema=SCHEMA)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table(UNAVAIL_TABLE, schema=SCHEMA):
        _drop_index_if_exists(inspector, UNAVAIL_TABLE, IDX_UNAVAIL_DATES)
        _drop_index_if_exists(inspector, UNAVAIL_TABLE, IDX_UNAVAIL_TENANT)
        if bind.dialect.name == "postgresql":
            op.execute(
                sa.text(
                    """
                    ALTER TABLE {qualified_table}
                    DROP CONSTRAINT IF EXISTS {constraint_name}
                    """.format(
                        qualified_table=f'"{SCHEMA}"."{UNAVAIL_TABLE}"',
                        constraint_name=EXCL_UNAVAILABILITY,
                    )
                )
            )
        op.drop_table(UNAVAIL_TABLE, schema=SCHEMA)

    inspector = sa.inspect(bind)
    if inspector.has_table(OWNER_TABLE, schema=SCHEMA):
        _drop_index_if_exists(inspector, OWNER_TABLE, IDX_OWNER_PHONE)
        _drop_index_if_exists(inspector, OWNER_TABLE, IDX_OWNER_TENANT)
        op.drop_table(OWNER_TABLE, schema=SCHEMA)
