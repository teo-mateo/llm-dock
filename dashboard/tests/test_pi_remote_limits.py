from pi_remote.limits import RateLimiter


KEY = ("s1", "i1")


def test_allows_up_to_the_limit():
    limiter = RateLimiter(max_events=3, window_ms=60000)
    assert limiter.allow(KEY, 0) is True
    assert limiter.allow(KEY, 1) is True
    assert limiter.allow(KEY, 2) is True


def test_rejects_beyond_the_limit():
    limiter = RateLimiter(max_events=3, window_ms=60000)
    for now in range(3):
        assert limiter.allow(KEY, now) is True
    assert limiter.allow(KEY, 3) is False


def test_window_slides():
    limiter = RateLimiter(max_events=2, window_ms=60000)
    assert limiter.allow(KEY, 0) is True
    assert limiter.allow(KEY, 1000) is True
    assert limiter.allow(KEY, 2000) is False
    assert limiter.allow(KEY, 60000) is True
    assert limiter.allow(KEY, 61000) is True
    assert limiter.allow(KEY, 62000) is False
