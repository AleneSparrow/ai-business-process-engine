"""Per-business SMS opt-out list.

Revision ID: 0021
Revises: 0020
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sms_suppressions",
        sa.Column("business_id", sa.String(128), nullable=False),
        sa.Column("phone_number", sa.String(64), nullable=False),
        sa.Column("suppressed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("business_id", "phone_number", name="pk_sms_suppressions"),
    )


def downgrade() -> None:
    op.drop_table("sms_suppressions")
