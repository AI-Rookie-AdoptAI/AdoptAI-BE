"""add STT pipeline state to chat sessions

Revision ID: 20260722_stt
Revises: 20260722_init
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa

revision = "20260722_stt"
down_revision = "20260722_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_sessions", sa.Column("stt_session_id", sa.String(), nullable=True))
    op.add_column("chat_sessions", sa.Column("stt_slots", sa.JSON(), nullable=True))
    op.create_index("ix_chat_sessions_stt_session_id", "chat_sessions", ["stt_session_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_sessions_stt_session_id", table_name="chat_sessions")
    op.drop_column("chat_sessions", "stt_slots")
    op.drop_column("chat_sessions", "stt_session_id")
