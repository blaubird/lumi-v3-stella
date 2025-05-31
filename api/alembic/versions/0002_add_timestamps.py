"""Add timestamps to tables
Revision ID: 0002_add_timestamps
Revises: 001_initial_schema
Create Date: 2025-05-28 14:48:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_add_timestamps'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None

def upgrade():
    # Update the updated_at column in tenants table to use automatic timestamp updates
    op.execute("""
    ALTER TABLE tenants 
    DROP COLUMN updated_at,
    ADD COLUMN updated_at TIMESTAMP DEFAULT now()
    """)
    
    # Create trigger function for automatic timestamp updates if it doesn't exist
    op.execute("""
    CREATE OR REPLACE FUNCTION update_modified_column()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = now();
        RETURN NEW;
    END;
    $$ language 'plpgsql';
    """)
    
    # Add trigger to tenants table
    op.execute("""
    DROP TRIGGER IF EXISTS update_tenants_updated_at ON tenants;
    CREATE TRIGGER update_tenants_updated_at
    BEFORE UPDATE ON tenants
    FOR EACH ROW
    EXECUTE FUNCTION update_modified_column();
    """)
    
    # Update the updated_at column in faqs table
    op.execute("""
    ALTER TABLE faqs 
    DROP COLUMN updated_at,
    ADD COLUMN updated_at TIMESTAMP DEFAULT now()
    """)
    
    # Add trigger to faqs table
    op.execute("""
    DROP TRIGGER IF EXISTS update_faqs_updated_at ON faqs;
    CREATE TRIGGER update_faqs_updated_at
    BEFORE UPDATE ON faqs
    FOR EACH ROW
    EXECUTE FUNCTION update_modified_column();
    """)

def downgrade():
    # Remove triggers
    op.execute("""
    DROP TRIGGER IF EXISTS update_tenants_updated_at ON tenants;
    DROP TRIGGER IF EXISTS update_faqs_updated_at ON faqs;
    """)
    
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
