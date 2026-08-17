"""Grant (or extend) a test/trial subscription for a business, bypassing
Lemon Squeezy checkout entirely -- for local/dev testing of the dashboard
before the real billing flow (store setup + a live checkout) is finished.

Sets the business's `subscription_status` to "on_trial" -- the same status
Lemon Squeezy itself would set for a real trial -- so `Business.has_billing_access`
(src/domain/tenancy.py) evaluates True and RequireActiveSubscription
(web/app/src/components/RouteGuards.tsx) stops redirecting the Overview and
Conversations tabs to /app/billing.

This talks directly to the database via DATABASE_URL and touches nothing
else -- no Lemon Squeezy API call, no webhook, no payment. It is meant to
be run by hand, by whoever owns DATABASE_URL (Alena), from a machine that
already has it configured (e.g. `railway run` or a local .env) -- it is
never run by, or with credentials shared to, an AI assistant.

Usage:
    DATABASE_URL=postgresql://... python scripts/grant_trial_access.py test-law-firm
    DATABASE_URL=postgresql://... python scripts/grant_trial_access.py test-law-firm --days 90 --plan pro

    # Or, if you already have a shell with Railway's Postgres attached:
    railway run python scripts/grant_trial_access.py test-law-firm
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.persistence.sqlalchemy_uow import (  # noqa: E402
    SQLAlchemyUnitOfWork,
    create_database_engine,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("business_id", help="The business's id (e.g. test-law-firm)")
    parser.add_argument("--days", type=int, default=30, help="Trial length in days from now (default: 30)")
    parser.add_argument("--plan", choices=["starter", "pro"], default="starter", help="Plan to display on Billing (default: starter)")
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is not set -- point it at the real database before running this.")

    engine = create_database_engine(database_url)
    factory = SQLAlchemyUnitOfWork.factory_for_engine(engine)
    trial_ends_at = datetime.now(timezone.utc) + timedelta(days=args.days)

    with factory() as uow:
        existing = uow.businesses.get(args.business_id)
        if existing is None:
            raise SystemExit(f"No business found with id {args.business_id!r}")
        print(f"Before: subscription_status={existing.subscription_status!r} plan={existing.plan!r}")

        updated = uow.businesses.update_billing(
            args.business_id,
            payment_customer_id=existing.payment_customer_id,
            payment_subscription_id=existing.payment_subscription_id,
            plan=args.plan,
            subscription_status="on_trial",
            trial_ends_at=trial_ends_at,
            current_period_end=existing.current_period_end,
        )
        uow.commit()
        print(f"After:  subscription_status={updated.subscription_status!r} plan={updated.plan!r} trial_ends_at={updated.trial_ends_at}")
        print("Dashboard access (Overview/Conversations) should now be unblocked for this business.")


if __name__ == "__main__":
    main()
