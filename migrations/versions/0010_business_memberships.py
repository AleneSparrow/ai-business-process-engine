"""Allow one staff account to be linked to more than one business.

Adds `business_memberships`, a many-to-many join table between staff_users
and businesses, and backfills it from every account's existing single
`staff_users.business_id`. That column is NOT dropped -- it keeps meaning
"this account's currently active business" (must be a member of this new
table, or null), so existing single-business accounts and any in-flight
requests keep working unchanged through the deploy. See
`src/persistence/business_provisioning_service.py` (BusinessProvisioningService.
create_business no longer rejects a second business) and
`src/api/dependencies.py` (require_own_business now checks membership in
this table rather than equality with the single business_id).

Revision ID: 0010
Revises: 0009
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "business_memberships",
        sa.Column("staff_user_id", sa.String(128), primary_key=True),
        sa.Column("business_id", sa.String(128), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["staff_user_id"], ["staff_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_business_memberships_business", "business_memberships", ["business_id"])

    # Backfill: every account already linked to a business becomes a member
    # of that one business.
    op.execute(
        """
        INSERT INTO business_memberships (staff_user_id, business_id, created_at)
        SELECT id, business_id, created_at
        FROM staff_users
        WHERE business_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_business_memberships_business", table_name="business_memberships")
    op.drop_table("business_memberships")
