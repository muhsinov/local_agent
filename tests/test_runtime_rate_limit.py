import threading

from app.runtime.rate_limit import FixedWindowRateLimiter


class Clock:
    def __init__(self, value=0.0):
        self.value = value

    def __call__(self):
        return self.value


def test_window_reset_and_expired_cleanup():
    clock = Clock()
    limiter = FixedWindowRateLimiter(clock=clock, max_buckets=10, cleanup_interval=1)
    assert limiter.check("read", "a", 1, 10).allowed
    assert not limiter.check("read", "a", 1, 10).allowed
    limiter.check("read", "b", 1, 10)
    clock.value = 11
    assert limiter.check("read", "a", 1, 10).allowed
    assert len(limiter._windows) == 1


def test_periodic_cleanup_bound_and_deterministic_eviction():
    clock = Clock()
    limiter = FixedWindowRateLimiter(clock=clock, max_buckets=3, cleanup_interval=2)
    for identity in ("a", "b", "c"):
        limiter.check("read", identity, 10, 100)
    clock.value = 1
    limiter.check("read", "a", 10, 100)
    limiter.check("read", "d", 10, 100)
    assert len(limiter._windows) <= 3
    assert ("read", "a") in limiter._windows
    assert ("read", "b") not in limiter._windows


def test_concurrent_checks_are_atomic_and_identities_are_independent():
    limiter = FixedWindowRateLimiter(clock=lambda: 1.0, max_buckets=100)
    results = []
    threads = [threading.Thread(target=lambda: results.append(limiter.check("chat", "browser-a", 10, 60))) for _ in range(20)]
    threads += [threading.Thread(target=lambda: results.append(limiter.check("chat", "browser-b", 10, 60))) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert limiter._windows[("chat", "browser-a")].count == 20
    assert limiter._windows[("chat", "browser-b")].count == 2
    assert all(result.reset_seconds > 0 for result in results)
    assert all("browser-a" not in repr(result) for result in results)
