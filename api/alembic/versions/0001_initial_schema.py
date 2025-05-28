"""Initial schema migration
Revision ID: 0001_initial
Revises: 
Create Date: 2025-05-28 14:47:00.000000
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Create extension for pgvector
    op.execute('CREATE EXTENSION IF NOT EXISTS vector;')
    
    # Create role enum type with idempotent approach
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'role_enum') THEN
            CREATE TYPE role_enum AS ENUM ('user', 'bot');
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
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
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
        sa.Column('role', sa.Enum('user', 'bot', name='role_enum'), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('tokens', sa.Integer(), nullable=True),
        sa.Column('ts', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
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
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_faqs_tenant_id'), 'faqs', ['tenant_id'], unique=False)

def downgrade():
    # Drop tables in reverse order
    op.drop_table('faqs')
    op.drop_table('messages')
    op.drop_table('tenants')
    
    # Drop enum type with idempotent approach
    op.execute("""
    DO $$
    BEGIN
        DROP TYPE role_enum;
    EXCEPTION
        WHEN undefined_object THEN NULL;
    END
    $$;
    """)
