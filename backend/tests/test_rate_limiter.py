from app.services.rate_limiter import RateLimitExceeded, RateLimiter


def test_allows_requests_up_to_capacity():
    limiter = RateLimiter(capacity=3, refill_per_minute=0)
    for _ in range(3):
        limiter.check("session-a")


def test_raises_once_capacity_exhausted():
    limiter = RateLimiter(capacity=2, refill_per_minute=0)
    limiter.check("session-a")
    limiter.check("session-a")
    try:
        limiter.check("session-a")
        assert False, "expected RateLimitExceeded"
    except RateLimitExceeded:
        pass


def test_sessions_have_independent_buckets():
    limiter = RateLimiter(capacity=1, refill_per_minute=0)
    limiter.check("session-a")
    limiter.check("session-b")  # separate bucket, should not raise


def test_refill_restores_tokens_over_time(monkeypatch):
    limiter = RateLimiter(capacity=1, refill_per_minute=60)  # 1 token/sec
    clock = {"now": 1000.0}
    monkeypatch.setattr("app.services.rate_limiter.time.monotonic", lambda: clock["now"])

    limiter.check("session-a")
    try:
        limiter.check("session-a")
        assert False, "expected RateLimitExceeded"
    except RateLimitExceeded:
        pass

    clock["now"] += 1.0
    limiter.check("session-a")  # refilled after 1 second
