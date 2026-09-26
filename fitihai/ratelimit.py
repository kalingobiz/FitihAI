"""Per-client sliding-window rate limiting (in memory, one process)."""

from __future__ import annotations

import threading
import time
from collections import deque


class RateLimiter:
    def __init__(self, per_minute: int, window_seconds: float = 60.0):
        self.per_minute = per_minute
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._last_sweep = time.monotonic()

    def allow(self, key: str, now: float | None = None) -> bool:
        """Record a request for ``key``; False if it is over the limit."""
        if self.per_minute <= 0:
            return True
        now = time.monotonic() if now is None else now
        cutoff = now - self.window
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.per_minute:
                return False
            hits.append(now)
            if now - self._last_sweep > self.window:
                # Forget idle clients so memory does not grow without bound.
                for k in [k for k, v in self._hits.items() if not v or v[-1] <= cutoff]:
                    del self._hits[k]
                self._last_sweep = now
            return True
