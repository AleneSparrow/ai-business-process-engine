"""Add SMS connection table (one Twilio phone number per business).

Its own table, not a Business DNA field -- same reasoning as
crm_webhook_connections (see 0007): the Twilio phone SID is an operational
credential-adjacent detail, not something that belongs in the AI's prompt
context. Unlike the CRM webhook (one optional URL a business types in),
the phone number here is purchased and populated by the backend itself via
SmsService.provision_number_if_needed -- see that module for why.

Revision ID: 0008
Revises: 0007
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sms_connections",
        sa.Column("business_id", sa.String(128), primary_key=True),
        sa.Column("phone_number", sa.String(32), nullable=False),
        sa.Column("twilio_phone_sid", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["business_id"], ["businesses.id"], ondelete="CASCADE",
            name="fk_sms_connections_business",
        ),
    )
    op.create_index(
        "uq_sms_connections_phone_number",
        "sms_connections",
        ["phone_number"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_sms_connections_phone_number", table_name="sms_connections")
    op.drop_table("sms_connections")
