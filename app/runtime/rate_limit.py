import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int


class FixedWindowRateLimiter:
    def __init__(self) -> None:
        self._windows: dict[tuple[str, str], tuple[int, int]] = {}
        self._lock = threading.Lock()

    def check(self, group: str, identity: str, limit: int, window_seconds: int) -> RateLimitResult:
        now = int(time.time())
        window = now // window_seconds
        key = (group, identity)
        with self._lock:
            current_window, count = self._windows.get(key, (window, 0))
            if current_window != window:
                count = 0
                current_window = window
            count += 1
            self._windows[key] = (current_window, count)
            reset = max(1, (current_window + 1) * window_seconds - now)
            return RateLimitResult(count <= limit, limit, max(0, limit - count), reset)
