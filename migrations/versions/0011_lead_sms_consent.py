"""Add leads.sms_consent (proactive follow-up SMS opt-in).

Explicit, sticky, per-lead consent gate for PersistentFollowUpRunner
(universal-sales-cycle-model.md section 8) -- set only from a deliberate
widget checkbox (see PublicConversationCreateRequest/
PublicConversationMessageRequest.sms_consent), never inferred by the AI from
conversation text. `server_default="false"` so every pre-existing lead
defaults to no-consent, not an implicit opt-in.

Revision ID: 0011
Revises: 0010
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("sms_consent", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("leads", "sms_consent")
