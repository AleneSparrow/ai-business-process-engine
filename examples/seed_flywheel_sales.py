"""Idempotently seed Flywheel as its own first customer.

The product's USP is inquiry-to-deal. This tenant is the sales cycle for
Flywheel itself: website visitors chat with the real engine, and the owner
(the first client) sees those conversations on the dashboard.

Does not create an account. To attach an existing login so the dashboard
shows these threads, set FLYWHEEL_OWNER_EMAIL to that account's email.

Allowed when APP_ENV is development/local, or when FLYWHEEL_SELF_SEED=1
(explicit production bootstrap for customer-zero). Never runs on deploy
by itself.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import Settings  # noqa: E402
from src.domain.auth import normalize_email  # noqa: E402
from src.domain.models import utc_now  # noqa: E402
from src.domain.tenancy import Business  # noqa: E402
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine  # noqa: E402

BUSINESS_ID = "flywheel"


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _plain_json(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_plain_json(item) for item in value]
    return value


def _allowed() -> bool:
    env = os.getenv("APP_ENV", "").strip().casefold()
    if env in {"development", "local"}:
        return True
    return os.getenv("FLYWHEEL_SELF_SEED", "").strip() == "1"


def main() -> None:
    if not _allowed():
        raise RuntimeError(
            "Refusing to seed the Flywheel sales tenant. Set APP_ENV=development "
            "or APP_ENV=local, or FLYWHEEL_SELF_SEED=1 for the one-time production bootstrap."
        )

    settings = Settings.from_environment()
    with (PROJECT_ROOT / "config" / "business_dna.flywheel.json").open(encoding="utf-8") as file:
        configuration = json.load(file)

    owner_email = os.getenv("FLYWHEEL_OWNER_EMAIL", "").strip()
    engine = create_database_engine(settings.database_url)
    factory = SQLAlchemyUnitOfWork.factory_for_engine(engine)
    linked = False
    try:
        with factory() as unit_of_work:
            business = unit_of_work.businesses.get(BUSINESS_ID)
            if business is None:
                now = utc_now()
                unit_of_work.businesses.add(
                    Business(BUSINESS_ID, configuration["business"]["name"], now, now, test_mode_enabled=True)
                )
            active_dna = unit_of_work.business_dna.get_active(BUSINESS_ID)
            if active_dna is None or _plain_json(active_dna.configuration) != configuration:
                unit_of_work.business_dna.add_version(BUSINESS_ID, configuration)
            if owner_email:
                owner = unit_of_work.staff_users.get_by_email(normalize_email(owner_email), for_update=True)
                if owner is None:
                    raise RuntimeError(
                        "FLYWHEEL_OWNER_EMAIL does not match an existing account. "
                        "Sign up first, then re-run the seed."
                    )
                if BUSINESS_ID not in owner.business_ids:
                    unit_of_work.staff_users.save(owner.with_business(BUSINESS_ID))
                    linked = True
            unit_of_work.commit()
    finally:
        engine.dispose()

    extra = " (dashboard linked)" if linked else ""
    print(f"Flywheel sales tenant is ready: {BUSINESS_ID}{extra}")
    print("Set VITE_SALES_BUSINESS_ID=flywheel on the frontend and redeploy.")


if __name__ == "__main__":
    main()
