"""Railway/background entry point for durable sales shadow jobs."""

import argparse
import time
from datetime import timedelta

from src.ai.runtime import build_ai_runtime
from src.config import Settings
from src.domain.models import utc_now
from src.persistence.sales_shadow_orchestrator import SalesShadowOrchestrator
from src.persistence.sales_shadow_service import SalesShadowService
from src.persistence.sales_shadow_worker import SalesShadowWorker
from src.persistence.sqlalchemy_uow import SQLAlchemyUnitOfWork, create_database_engine


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--retention-days", type=int, default=30)
    args = parser.parse_args()
    settings = Settings.from_environment()
    runtime = build_ai_runtime(settings)
    factory = SQLAlchemyUnitOfWork.factory_for_engine(
        create_database_engine(settings.database_url))
    orchestrator = None
    if runtime.sales_response_generator is not None:
        orchestrator = SalesShadowOrchestrator(
            runtime.sales_response_generator, SalesShadowService(factory))
    worker = SalesShadowWorker(factory, runtime.sales_turn_analyzer, orchestrator)
    with factory() as uow:
        uow.sales_shadow_jobs.delete_completed_before(
            before=utc_now() - timedelta(days=max(1, args.retention_days)))
        uow.commit()
    while True:
        worked = worker.run_one(now=utc_now())
        if args.once:
            return 0
        if not worked:
            time.sleep(max(0.1, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
