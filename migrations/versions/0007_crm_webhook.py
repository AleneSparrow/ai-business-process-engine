"""Add CRM webhook connection table (e.g. Clio) -- kept out of Business DNA
deliberately, since Business DNA flows into AI prompt context (BUSINESS_CONTEXT)
and this URL is effectively a bearer secret (Zapier/Make-style catch hooks
embed a token in the path).

Revision ID: 0007
Revises: 0006
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crm_webhook_connections",
        sa.Column("business_id", sa.String(128), primary_key=True),
        sa.Column("webhook_url", sa.String(2048), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["business_id"], ["businesses.id"], ondelete="CASCADE",
            name="fk_crm_webhook_connections_business",
        ),
    )


def downgrade() -> None:
    op.drop_table("crm_webhook_connections")
