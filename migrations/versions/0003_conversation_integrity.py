"""Strengthen conversation timestamp and message idempotency invariants.

Revision ID: 0003
Revises: 0002
"""

from typing import Sequence

from alembic import op


revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_conversations_timestamp_order",
        "conversations",
        "updated_at >= created_at AND last_activity_at >= created_at",
    )
    op.create_check_constraint(
        "ck_conversations_revocation_order",
        "conversations",
        "token_revoked_at IS NULL OR token_revoked_at >= created_at",
    )
    op.create_check_constraint(
        "ck_conversation_messages_idempotency_pair",
        "conversation_messages",
        "(external_message_id IS NULL AND content_fingerprint IS NULL) OR "
        "(external_message_id IS NOT NULL AND content_fingerprint IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_conversation_messages_idempotency_pair",
        "conversation_messages",
        type_="check",
    )
    op.drop_constraint(
        "ck_conversations_revocation_order",
        "conversations",
        type_="check",
    )
    op.drop_constraint(
        "ck_conversations_timestamp_order",
        "conversations",
        type_="check",
    )
