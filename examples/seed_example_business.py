"""Idempotently seed the example tenant into an already migrated development database."""

import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import Settings  # noqa: E402
from src.domain.models import utc_now  # noqa: E402
from src.domain.tenancy import Business  # noqa: E402
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine  # noqa: E402


BUSINESS_ID = "acme-home-services"


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _plain_json(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_plain_json(item) for item in value]
    return value


def main() -> None:
    settings = Settings.from_environment()
    explicit_app_env = os.getenv("APP_ENV", "").strip().casefold()
    if explicit_app_env not in {"development", "local"}:
        raise RuntimeError(
            "development seed requires APP_ENV=development or APP_ENV=local explicitly"
        )
    with (PROJECT_ROOT / "config" / "business_dna.example.json").open(encoding="utf-8") as file:
        configuration = json.load(file)

    engine = create_database_engine(settings.database_url)
    factory = SQLAlchemyUnitOfWork.factory_for_engine(engine)
    try:
        with factory() as unit_of_work:
            business = unit_of_work.businesses.get(BUSINESS_ID)
            if business is None:
                now = utc_now()
                unit_of_work.businesses.add(
                    Business(BUSINESS_ID, configuration["business"]["name"], now, now)
                )
            active_dna = unit_of_work.business_dna.get_active(BUSINESS_ID)
            if active_dna is None or _plain_json(active_dna.configuration) != configuration:
                unit_of_work.business_dna.add_version(BUSINESS_ID, configuration)
            unit_of_work.commit()
    finally:
        engine.dispose()
    print(f"Example business is ready: {BUSINESS_ID}")


if __name__ == "__main__":
    main()
