"""Drop the unique constraint on businesses.payment_customer_id.

The same real person can run more than one business through this app under
one Lemon Squeezy account (e.g. an owner testing with a second business, or
in principle any agency-style user) -- Lemon Squeezy assigns one customer_id
per *email*, not per subscription, so a second business checking out under
the same email reuses the first business's customer_id. The webhook handler
(BillingService._apply_subscription_snapshot) always resolves which business
an event belongs to via `custom_data.business_id` -- set on every checkout
this app creates -- so payment_customer_id is only ever a secondary, rarely-
used fallback lookup (see `_resolve_business_id`), never load-bearing for
correctness. The unique index made that impossible: a second business's very
first webhook (subscription_created) crashed the whole webhook handler with
an IntegrityError -- silently leaving that business stuck on
subscription_status="incomplete" forever, since Lemon Squeezy did retry the
delivery but every retry hit the same constraint. Discovered live: a real
test checkout for a second business (customer_id shared with an earlier one)
returned repeated 500s in production.

Revision ID: 0009
Revises: 0008
"""

from typing import Sequence

from alembic import op


revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("uq_businesses_payment_customer_id", table_name="businesses")
    op.create_index(
        "ix_businesses_payment_customer_id",
        "businesses",
        ["payment_customer_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_businesses_payment_customer_id", table_name="businesses")
    op.create_index(
        "uq_businesses_payment_customer_id",
        "businesses",
        ["payment_customer_id"],
        unique=True,
    )
