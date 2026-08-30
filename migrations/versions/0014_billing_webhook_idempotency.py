"""Billing webhook duplicate/out-of-order protection.

Two production-risk gaps in BillingService.handle_webhook: it applied every
correctly-signed Lemon Squeezy event unconditionally, so (1) a retried
delivery (Lemon Squeezy resends on anything but a 2xx, or just occasionally)
was reapplied from scratch, and (2) events are not guaranteed to arrive in
the order Lemon Squeezy generated them -- a delayed subscription_created/
updated retry landing after a subscription_cancelled/expired could resurrect
access that was already correctly revoked.

- `billing_webhook_events` is a dedup ledger keyed by a fingerprint of the
  (already signature-verified) raw payload bytes -- Lemon Squeezy gives
  webhooks no delivery-specific id, but a retry resends identical bytes, so
  the fingerprint is exact. Stores no payload or customer data, only the
  fingerprint and the event name.
- `businesses.billing_event_at` is the "as of" timestamp of the last webhook
  event actually applied to that business's billing fields (the
  subscription/invoice snapshot's own updated_at, falling back to
  created_at). BusinessRepository.update_billing refuses to apply an event
  whose own timestamp is older than this watermark.

Revision ID: 0014
Revises: 0013
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("businesses", sa.Column("billing_event_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "billing_webhook_events",
        sa.Column("event_fingerprint", sa.String(64), primary_key=True),
        sa.Column("event_name", sa.String(64), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("billing_webhook_events")
    op.drop_column("businesses", "billing_event_at")
