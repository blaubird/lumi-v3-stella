"""Add timestamps to tables
Revision ID: 0002_add_timestamps
Revises: 001_initial_schema
Create Date: 2025-05-28 14:48:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '0002_add_timestamps'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None

def upgrade():
    # Check if updated_at column exists in tenants table before attempting to drop
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tenants_columns = [col['name'] for col in inspector.get_columns('tenants')]
    faqs_columns = [col['name'] for col in inspector.get_columns('faqs')]
    
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
    
    # Handle tenants table
    if 'updated_at' in tenants_columns:
        # Drop and recreate the column if it exists
        op.execute("""
        ALTER TABLE tenants 
        DROP COLUMN updated_at,
        ADD COLUMN updated_at TIMESTAMP DEFAULT now()
        """)
    else:
        # Just add the column if it doesn't exist
        op.execute("""
        ALTER TABLE tenants 
        ADD COLUMN updated_at TIMESTAMP DEFAULT now()
        """)
    
    # Add trigger to tenants table
    op.execute("""
    DROP TRIGGER IF EXISTS update_tenants_updated_at ON tenants;
    CREATE TRIGGER update_tenants_updated_at
    BEFORE UPDATE ON tenants
    FOR EACH ROW
    EXECUTE FUNCTION update_modified_column();
    """)
    
    # Handle faqs table
    if 'updated_at' in faqs_columns:
        # Drop and recreate the column if it exists
        op.execute("""
        ALTER TABLE faqs 
        DROP COLUMN updated_at,
        ADD COLUMN updated_at TIMESTAMP DEFAULT now()
        """)
    else:
        # Just add the column if it doesn't exist
        op.execute("""
        ALTER TABLE faqs 
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
    # Remove triggers - always safe with IF EXISTS
    op.execute("""
    DROP TRIGGER IF EXISTS update_tenants_updated_at ON tenants;
    DROP TRIGGER IF EXISTS update_faqs_updated_at ON faqs;
    """)
    
    # Check if columns exist before attempting operations
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tenants_columns = [col['name'] for col in inspector.get_columns('tenants')]
    faqs_columns = [col['name'] for col in inspector.get_columns('faqs')]
    
    # Handle tenants table
    if 'updated_at' in tenants_columns:
        op.execute("""
        ALTER TABLE tenants 
        DROP COLUMN updated_at,
        ADD COLUMN updated_at TIMESTAMP DEFAULT now()
        """)
    
    # Handle faqs table
    if 'updated_at' in faqs_columns:
        op.execute("""
        ALTER TABLE faqs 
        DROP COLUMN updated_at,
        ADD COLUMN updated_at TIMESTAMP DEFAULT now()
        """)
