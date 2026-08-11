"""Small abuse-control boundary for anonymous public chat."""

from collections import defaultdict, deque
from threading import Lock
from time import monotonic
from typing import Protocol


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
