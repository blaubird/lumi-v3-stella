"""Consolidated schema migration
Revision ID: 001_initial_schema
Revises: 
Create Date: 2025-05-31 12:57:00.000000

"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create extension for pgvector with idempotent approach
    op.execute('CREATE EXTENSION IF NOT EXISTS vector;')
    
    # Create role enum type with idempotent approach
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'role_enum') THEN
            CREATE TYPE role_enum AS ENUM ('user', 'bot', 'inbound', 'assistant');
        END IF;
    EXCEPTION
        WHEN duplicate_object THEN NULL;
    END
    $$;
    """)
    
    # Add values to existing enum if it already exists
    op.execute("ALTER TYPE role_enum ADD VALUE IF NOT EXISTS 'inbound';")
    op.execute("ALTER TYPE role_enum ADD VALUE IF NOT EXISTS 'assistant';")
    
    # Create direction enum type with idempotent approach
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'direction_enum') THEN
            CREATE TYPE direction_enum AS ENUM ('inbound', 'outbound');
        END IF;
    EXCEPTION
        WHEN duplicate_object THEN NULL;
    END
    $$;
    """)
    
    # Create tenants table
    op.create_table(
        'tenants',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('phone_id', sa.String(), nullable=False),
        sa.Column('wh_token', sa.Text(), nullable=False),
        sa.Column('system_prompt', sa.Text(), server_default='You are a helpful assistant.'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tenants_id'), 'tenants', ['id'], unique=False)
    op.create_index(op.f('ix_tenants_phone_id'), 'tenants', ['phone_id'], unique=True)
    
    # Create messages table
    op.create_table(
        'messages',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('wa_msg_id', sa.String(), nullable=True),
        sa.Column('role', sa.Enum('user', 'bot', 'inbound', 'assistant', name='role_enum'), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('tokens', sa.Integer(), nullable=True),
        sa.Column('ts', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('wa_msg_id')
    )
    op.create_index(op.f('ix_messages_tenant_id'), 'messages', ['tenant_id'], unique=False)
    
    # Create faqs table
    op.create_table(
        'faqs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('embedding', Vector(1536), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_faqs_tenant_id'), 'faqs', ['tenant_id'], unique=False)
    
    # Create usage table
    op.create_table(
        'usage',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('direction', sa.Enum('inbound', 'outbound', name='direction_enum'), nullable=False),
        sa.Column('tokens', sa.Integer(), nullable=False),
        sa.Column('msg_ts', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_usage_tenant_id'), 'usage', ['tenant_id'], unique=False)
    
    # Ensure foreign key constraints have ON DELETE CASCADE
    op.execute("""
    DO $$
    BEGIN
        -- Drop existing constraint if it exists
        IF EXISTS (
            SELECT 1 FROM information_schema.table_constraints 
            WHERE constraint_name = 'faqs_tenant_id_fkey' AND table_name = 'faqs'
        ) THEN
            ALTER TABLE faqs DROP CONSTRAINT faqs_tenant_id_fkey;
        END IF;
        
        -- Add constraint with CASCADE
        ALTER TABLE faqs 
        ADD CONSTRAINT faqs_tenant_id_fkey 
        FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
    EXCEPTION
        WHEN undefined_object THEN NULL;
    END
    $$;
    """)


def downgrade():
    # Drop tables in reverse order
    op.drop_table('usage')
    op.drop_table('faqs')
    op.drop_table('messages')
    op.drop_table('tenants')
    
    # Drop enum types with idempotent approach
    op.execute("""
    DO $$
    BEGIN
        DROP TYPE direction_enum;
    EXCEPTION
        WHEN undefined_object THEN NULL;
    END
    $$;
    """)
    
    op.execute("""
    DO $$
    BEGIN
        DROP TYPE role_enum;
    EXCEPTION
        WHEN undefined_object THEN NULL;
    END
    $$;
    """)
