"""Track direct-to-object-storage upload finalization state.

Revision ID: 004_dataset_upload_state
Revises: 003_add_user_sessions
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "004_dataset_upload_state"
down_revision: Union[str, None] = "003_add_user_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "datasets",
        sa.Column("upload_status", sa.String(length=20), nullable=False, server_default="ready"),
    )
    op.add_column(
        "datasets",
        sa.Column("upload_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("datasets", "upload_expires_at")
    op.drop_column("datasets", "upload_status")
