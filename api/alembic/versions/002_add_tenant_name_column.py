"""Add name column to tenants table
Revision ID: 002_add_tenant_name_column
Revises: 001_initial_schema
Create Date: 2025-05-28 11:41:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002_add_tenant_name_column'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None

def upgrade():
    # Add name column to tenants table
    op.add_column('tenants', sa.Column('name', sa.String(255), nullable=False, server_default='Default Tenant'))
    
    # Remove server_default after all rows are updated
    op.alter_column('tenants', 'name', server_default=None)

def downgrade():
    # Remove name column from tenants table
    op.drop_column('tenants', 'name')
