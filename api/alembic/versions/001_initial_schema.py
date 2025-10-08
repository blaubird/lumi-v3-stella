"""Consolidated schema migration
Revision ID: 001_initial_schema
Revises:
Create Date: 2025-05-31 12:57:00.000000

"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    dialect = conn.dialect.name

    if dialect == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    if dialect == "postgresql":
        op.execute(
            """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'role_enum') THEN
            CREATE TYPE role_enum AS ENUM ('inbound', 'assistant');
        ELSE
            PERFORM 1 FROM pg_enum WHERE enumlabel='inbound' AND enumtypid = 'role_enum'::regtype;
            IF NOT FOUND THEN
                ALTER TYPE role_enum ADD VALUE 'inbound';
            END IF;
            PERFORM 1 FROM pg_enum WHERE enumlabel='assistant' AND enumtypid = 'role_enum'::regtype;
            IF NOT FOUND THEN
                ALTER TYPE role_enum ADD VALUE 'assistant';
            END IF;
        END IF;
    EXCEPTION
        WHEN duplicate_object THEN NULL;
    END
    $$;
            """
        )

        op.execute(
            """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'direction_enum') THEN
            CREATE TYPE direction_enum AS ENUM ('inbound', 'outbound');
        END IF;
    EXCEPTION
        WHEN duplicate_object THEN NULL;
    END
    $$;
            """
        )

    # Create tenants table
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("phone_id", sa.String(), nullable=False),
        sa.Column("wh_token", sa.Text(), nullable=False),
        sa.Column(
            "system_prompt", sa.Text(), server_default="You are a helpful assistant."
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tenants_id"), "tenants", ["id"], unique=False)
    op.create_index(op.f("ix_tenants_phone_id"), "tenants", ["phone_id"], unique=True)

    # Create messages table
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("wa_msg_id", sa.String(), nullable=True),
        sa.Column(
            "role", sa.Enum("inbound", "assistant", name="role_enum"), nullable=False
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=True),
        sa.Column("ts", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("wa_msg_id"),
    )
    op.create_index(
        op.f("ix_messages_tenant_id"), "messages", ["tenant_id"], unique=False
    )

    # Create faqs table
    op.create_table(
        "faqs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column(
            "question", sa.String(), nullable=False
        ),  # Changed from Text to String for exact matching
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_faqs_tenant_id"), "faqs", ["tenant_id"], unique=False)

    # Create usage table
    op.create_table(
        "usage",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column(
            "direction",
            sa.Enum("inbound", "outbound", name="direction_enum"),
            nullable=False,
        ),
        sa.Column("tokens", sa.Integer(), nullable=False),
        sa.Column("msg_ts", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column(
            "prompt_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "completion_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("trace_id", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_usage_tenant_id"), "usage", ["tenant_id"], unique=False)

    if dialect == "postgresql":
        op.execute(
            """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'appt_status_enum') THEN
            CREATE TYPE appt_status_enum AS ENUM ('pending', 'confirmed', 'cancelled');
        END IF;
    EXCEPTION
        WHEN duplicate_object THEN NULL;
    END
    $$;
            """
        )

    op.create_table(
        "appointments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(), nullable=False, index=True),
        sa.Column("customer_phone", sa.String(), nullable=False),
        sa.Column("customer_email", sa.String(), nullable=True),
        sa.Column("starts_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "confirmed", "cancelled", name="appt_status_enum"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("google_event_id", sa.String(), nullable=True),
        sa.Column(
            "reminded", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_ts",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )

    if dialect == "postgresql":
        op.execute(
            """
    UPDATE public.usage
       SET msg_ts = to_timestamp(msg_ts::bigint)
     WHERE pg_typeof(msg_ts) <> 'timestamp with time zone';
            """
        )

        op.execute(
            """
    ALTER TABLE public.faqs DROP CONSTRAINT IF EXISTS faqs_tenant_id_fkey;
    ALTER TABLE public.faqs
      ADD CONSTRAINT faqs_tenant_id_fkey
      FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;

    ALTER TABLE public.messages DROP CONSTRAINT IF EXISTS messages_tenant_id_fkey;
    ALTER TABLE public.messages
      ADD CONSTRAINT messages_tenant_id_fkey
      FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;

    ALTER TABLE public.usage DROP CONSTRAINT IF EXISTS usage_tenant_id_fkey;
    ALTER TABLE public.usage
      ADD CONSTRAINT usage_tenant_id_fkey
      FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;
            """
        )


def downgrade():
    conn = op.get_bind()
    dialect = conn.dialect.name

    op.drop_table("appointments")
    if dialect == "postgresql":
        op.execute("DROP TYPE IF EXISTS appt_status_enum")

    op.drop_table("usage")
    op.drop_table("faqs")
    op.drop_table("messages")
    op.drop_index(op.f("ix_tenants_phone_id"), table_name="tenants")
    op.drop_index(op.f("ix_tenants_id"), table_name="tenants")
    op.drop_table("tenants")

    if dialect == "postgresql":
        op.execute("DROP TYPE IF EXISTS direction_enum")
        op.execute("DROP TYPE IF EXISTS role_enum")
        op.execute("DROP EXTENSION IF EXISTS vector")
