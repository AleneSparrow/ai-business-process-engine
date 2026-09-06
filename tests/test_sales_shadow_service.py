from datetime import datetime, timezone

import pytest

from src.domain.sales import SalesMove, SalesShadowStatus
from src.persistence.sales_shadow_service import SalesShadowIdentity, SalesShadowService


def test_error_record_rejects_non_error_status() -> None:
    service = SalesShadowService(lambda: None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="error result requires"):
        service.record_error(
            SalesShadowIdentity("b", "c", "conversation", "message"),
            approved_move=SalesMove.HANDOFF_TO_HUMAN,
            status=SalesShadowStatus.VALID,
            violation="bad output",
            delivered_response_text=None,
            model_name=None,
            now=datetime.now(timezone.utc),
        )
