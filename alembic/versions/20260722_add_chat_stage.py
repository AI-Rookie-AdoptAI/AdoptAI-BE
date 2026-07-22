"""persist the chat workflow stage

Revision ID: 20260722_stage
Revises: 20260722_stt
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa

revision = "20260722_stage"
down_revision = "20260722_stt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column("stage", sa.String(), nullable=False, server_default="start"),
    )


def downgrade() -> None:
    op.drop_column("chat_sessions", "stage")
