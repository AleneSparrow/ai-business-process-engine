from datetime import timezone

from sqlalchemy import select

from src.api.rate_limit import InMemorySlidingWindowRateLimiter, SqlSlidingWindowRateLimiter
from src.persistence.sqlalchemy_models import Base, RateLimitHitRow
from src.persistence.sqlalchemy_uow import create_database_engine


def test_in_memory_limiter_blocks_after_window_fills() -> None:
    limiter = InMemorySlidingWindowRateLimiter(2, 60)
    assert limiter.allow("k") is True
    assert limiter.allow("k") is True
    assert limiter.allow("k") is False


def test_sql_limiter_is_shared_across_instances(tmp_path) -> None:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'rate.db'}")
    Base.metadata.create_all(engine)
    first = SqlSlidingWindowRateLimiter(engine, 1, 60)
    second = SqlSlidingWindowRateLimiter(engine, 1, 60)
    assert first.allow("chat:1") is True
    assert second.allow("chat:1") is False
    with engine.connect() as connection:
        count = connection.scalar(select(RateLimitHitRow.id))
        assert count is not None
    engine.dispose()
