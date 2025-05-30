"""Add usage table

Revision ID: 0003_add_usage_table
Revises: 0002_add_timestamps
Create Date: 2025-05-30 14:44:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0003_add_usage_table'
down_revision = '0002_add_timestamps'
branch_labels = None
depends_on = None


def upgrade():
    # Create direction enum type
    op.execute("CREATE TYPE direction_enum AS ENUM('inbound', 'outbound')")
    
    # Create usage table
    op.create_table(
        'usage',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('tenant_id', sa.String, sa.ForeignKey('tenants.id'), nullable=False, index=True),
        sa.Column('direction', sa.Enum('inbound', 'outbound', name='direction_enum'), nullable=False),
        sa.Column('tokens', sa.Integer, nullable=False),
        sa.Column('msg_ts', sa.TIMESTAMP, nullable=False, server_default=sa.func.now())
    )


def downgrade():
    # Drop usage table
    op.drop_table('usage')
    
    # Drop direction enum type
    op.execute("DROP TYPE direction_enum")
