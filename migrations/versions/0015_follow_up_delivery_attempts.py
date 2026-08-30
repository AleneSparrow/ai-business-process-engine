"""Durable outbox for proactive follow-up SMS delivery.

PersistentFollowUpRunner._send_one used to call Twilio, then persist
FOLLOW_UP_SENT on the case afterward -- if that save/commit failed for any
reason after a successful send (StaleCaseError aside, any DB hiccup), the
case's attempt count never advanced, so the next sweep saw the same case as
still due and sent another SMS. Every subsequent sweep would repeat this
indefinitely, since nothing recorded that a message had already gone out.

`follow_up_delivery_attempts` is claimed (INSERT ... ON CONFLICT DO NOTHING)
*before* Twilio is ever called, keyed by the natural idempotency key
(business_id, case_id, attempt_number). A retried sweep for the same attempt
gets back the already-claimed row instead of creating a second one, and its
`status`/`twilio_sid` say whether that attempt already reached Twilio -- see
FollowUpDeliveryAttemptRow and PersistentFollowUpRunner._send_one for why
this narrows (rather than eliminates -- Twilio's API has no client-supplied
idempotency key) the window for a duplicate send.

Revision ID: 0015
Revises: 0014
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "follow_up_delivery_attempts",
        sa.Column("business_id", sa.String(128), primary_key=True),
        sa.Column("case_id", sa.String(128), primary_key=True),
        sa.Column("attempt_number", sa.Integer, primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("message_text", sa.Text, nullable=False),
        sa.Column("twilio_sid", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["business_id", "case_id"],
            ["process_cases.business_id", "process_cases.id"],
            ondelete="CASCADE",
            name="fk_follow_up_delivery_attempts_tenant_case",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'SENT', 'FAILED')",
            name="ck_follow_up_delivery_attempts_status",
        ),
    )


def downgrade() -> None:
    op.drop_table("follow_up_delivery_attempts")
