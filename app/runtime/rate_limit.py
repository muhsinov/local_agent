import threading
import time
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int


@dataclass
class _Bucket:
    window_id: int
    count: int
    expires_at: float
    last_seen: float


class FixedWindowRateLimiter:
    def __init__(self, clock: Callable[[], float] | None = None, max_buckets: int = 10000, cleanup_interval: int = 64) -> None:
        self._clock = clock or time.monotonic
        self._max_buckets = max(1, max_buckets)
        self._cleanup_interval = max(1, cleanup_interval)
        self._checks = 0
        self._windows: dict[tuple[str, str], _Bucket] = {}
        self._lock = threading.Lock()

    def _cleanup_expired(self, now: float) -> None:
        for key, bucket in list(self._windows.items()):
            if bucket.expires_at <= now:
                self._windows.pop(key, None)

    def check(self, group: str, identity: str, limit: int, window_seconds: int) -> RateLimitResult:
        now = float(self._clock())
        window = int(now // window_seconds)
        key = (group, identity)
        with self._lock:
            self._checks += 1
            if self._checks % self._cleanup_interval == 0:
                self._cleanup_expired(now)
            current = self._windows.get(key)
            if current is None or current.window_id != window or current.expires_at <= now:
                current = _Bucket(window, 0, (window + 1) * window_seconds, now)
            if key not in self._windows and len(self._windows) >= self._max_buckets:
                self._cleanup_expired(now)
                if len(self._windows) >= self._max_buckets:
                    victim = min(self._windows, key=lambda item: (self._windows[item].last_seen, item[0], item[1]))
                    self._windows.pop(victim, None)
            current.count += 1
            current.last_seen = now
            self._windows[key] = current
            reset = max(1, int(current.expires_at - now + 0.999999))
            return RateLimitResult(current.count <= limit, limit, max(0, limit - current.count), reset)
