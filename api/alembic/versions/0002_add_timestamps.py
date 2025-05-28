"""Add timestamps to tables
Revision ID: 0002_add_timestamps
Revises: 0001_initial
Create Date: 2025-05-28 14:48:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_add_timestamps'
down_revision = '0001_initial'
branch_labels = None
depends_on = None

def upgrade():
    # Update the updated_at column in tenants table to use on update now()
    op.execute("""
    ALTER TABLE tenants 
    DROP COLUMN updated_at,
    ADD COLUMN updated_at TIMESTAMP DEFAULT now() ON UPDATE now()
    """)
    
    # Update the updated_at column in faqs table to use on update now()
    op.execute("""
    ALTER TABLE faqs 
    DROP COLUMN updated_at,
    ADD COLUMN updated_at TIMESTAMP DEFAULT now() ON UPDATE now()
    """)

def downgrade():
    # Revert the updated_at columns to standard timestamps
    op.execute("""
    ALTER TABLE tenants 
    DROP COLUMN updated_at,
    ADD COLUMN updated_at TIMESTAMP DEFAULT now()
    """)
    
    op.execute("""
    ALTER TABLE faqs 
    DROP COLUMN updated_at,
    ADD COLUMN updated_at TIMESTAMP DEFAULT now()
    """)
