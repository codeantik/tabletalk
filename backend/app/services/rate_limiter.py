"""In-memory per-session token-bucket rate limiting for the chat endpoint.

A PoC-scale abuse guard: each session gets its own bucket so one heavy user
can't starve others. State lives in process memory only, mirroring
session_manager's in-memory design -- a production deployment running
multiple backend workers would need a shared store (e.g. Redis) instead.
"""

import time
from dataclasses import dataclass


@dataclass
class _Bucket:
    tokens: float
    last_refill: float


class RateLimitExceeded(Exception):
    """A session has exhausted its request budget."""


class RateLimiter:
    def __init__(self, capacity: int, refill_per_minute: float):
        self._capacity = capacity
        self._refill_per_second = refill_per_minute / 60.0
        self._buckets: dict[str, _Bucket] = {}

    def _refill(self, bucket: _Bucket, now: float) -> None:
        elapsed = now - bucket.last_refill
        bucket.tokens = min(self._capacity, bucket.tokens + elapsed * self._refill_per_second)
        bucket.last_refill = now

    def check(self, session_id: str) -> None:
        """Consume one token for `session_id`. Raises RateLimitExceeded if
        the bucket is empty; leaves the bucket untouched in that case."""
        now = time.monotonic()
        bucket = self._buckets.setdefault(
            session_id, _Bucket(tokens=float(self._capacity), last_refill=now)
        )
        self._refill(bucket, now)
        if bucket.tokens < 1:
            raise RateLimitExceeded(f"Rate limit exceeded for session {session_id}")
        bucket.tokens -= 1


_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        from app.core.config import get_settings

        settings = get_settings()
        _limiter = RateLimiter(
            capacity=settings.rate_limit_capacity,
            refill_per_minute=settings.rate_limit_refill_per_minute,
        )
    return _limiter
