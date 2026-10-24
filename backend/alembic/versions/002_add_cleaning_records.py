"""Add cleaning_records table
Revision ID: 002_add_cleaning_records
Revises: 001_initial_schema
Create Date: 2026-10-24 18:10:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '002_add_cleaning_records'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cleaning_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dataset_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), server_default='completed', nullable=False),
        sa.Column('cleaning_config', sa.JSON(), nullable=False),
        sa.Column('cleaning_summary', sa.JSON(), nullable=False),
        sa.Column('output_filename', sa.String(length=255), nullable=True),
        sa.Column('output_file_path', sa.String(length=512), nullable=True),
        sa.Column('output_file_size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('output_row_count', sa.Integer(), nullable=True),
        sa.Column('output_column_count', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.String(length=1000), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['dataset_id'], ['datasets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_cleaning_records_id'), 'cleaning_records', ['id'], unique=False)
    op.create_index(op.f('ix_cleaning_records_dataset_id'), 'cleaning_records', ['dataset_id'], unique=False)
    op.create_index(op.f('ix_cleaning_records_user_id'), 'cleaning_records', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_cleaning_records_user_id'), table_name='cleaning_records')
    op.drop_index(op.f('ix_cleaning_records_dataset_id'), table_name='cleaning_records')
    op.drop_index(op.f('ix_cleaning_records_id'), table_name='cleaning_records')
    op.drop_table('cleaning_records')
