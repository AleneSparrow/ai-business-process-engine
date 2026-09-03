"""Small abuse-control boundary for anonymous public chat."""

import hashlib
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from threading import Lock
from time import monotonic
from typing import Protocol

from sqlalchemy import Engine, delete, func, select, text
from sqlalchemy.orm import Session

from src.persistence.sqlalchemy_models import RateLimitHitRow


class RateLimiter(Protocol):
    def allow(self, key: str) -> bool: ...


class InMemorySlidingWindowRateLimiter:
    """Thread-safe single-process limiter; multi-worker deployments need shared storage."""

    def __init__(self, requests: int, window_seconds: int, *, max_keys: int = 10_000) -> None:
        if requests < 1 or window_seconds < 1:
            raise ValueError("rate limit and window must be positive")
        self.requests = requests
        self.window_seconds = window_seconds
        if max_keys < 1:
            raise ValueError("max_keys must be positive")
        self.max_keys = max_keys
        self._entries: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            if key not in self._entries and len(self._entries) >= self.max_keys:
                for stored_key in tuple(self._entries):
                    stored_entries = self._entries[stored_key]
                    while stored_entries and stored_entries[0] <= cutoff:
                        stored_entries.popleft()
                    if not stored_entries:
                        del self._entries[stored_key]
                if len(self._entries) >= self.max_keys:
                    return False
            entries = self._entries[key]
            while entries and entries[0] <= cutoff:
                entries.popleft()
            if len(entries) >= self.requests:
                return False
            entries.append(now)
            return True


class SqlSlidingWindowRateLimiter:
    """Database-backed limiter so multiple app workers share one window."""

    def __init__(self, engine: Engine, requests: int, window_seconds: int) -> None:
        if requests < 1 or window_seconds < 1:
            raise ValueError("rate limit and window must be positive")
        self.engine = engine
        self.requests = requests
        self.window_seconds = window_seconds

    def allow(self, key: str) -> bool:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.window_seconds)
        lock_id = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big") % (2**63)
        with Session(self.engine) as session:
            with session.begin():
                if session.get_bind().dialect.name == "postgresql":
                    session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})
                session.execute(
                    delete(RateLimitHitRow).where(
                        RateLimitHitRow.rate_key == key,
                        RateLimitHitRow.occurred_at < cutoff,
                    )
                )
                count = session.scalar(
                    select(func.count()).select_from(RateLimitHitRow).where(
                        RateLimitHitRow.rate_key == key,
                        RateLimitHitRow.occurred_at >= cutoff,
                    )
                ) or 0
                if count >= self.requests:
                    return False
                session.add(RateLimitHitRow(rate_key=key, occurred_at=now))
                return True

