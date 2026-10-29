"""A small in-memory limit on how often something may happen, for the one process that serves this app."""

import time
from collections import deque


class RateLimiter:
    """At most `limit` events in any `window` seconds. Not shared between processes: there is only one."""

    def __init__(self, limit: int, window: float, clock=time.monotonic) -> None:
        self._limit = limit
        self._window = window
        self._clock = clock
        self._events: deque[float] = deque()

    def allow(self) -> bool:
        """Record an event and say whether it is within the limit."""
        now = self._clock()
        while self._events and now - self._events[0] >= self._window:
            self._events.popleft()
        if len(self._events) >= self._limit:
            return False
        self._events.append(now)
        return True

    def retry_after(self) -> int:
        if not self._events:
            return 0
        return max(1, int(self._window - (self._clock() - self._events[0])) + 1)
