"""Per-host minimum-interval rate limiter (polite scraping)."""

from __future__ import annotations

import threading
import time
from urllib.parse import urlsplit


class PerHostRateLimiter:
    def __init__(self, min_interval_s: float):
        self.min_interval_s = min_interval_s
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, url: str, *, sleep=time.sleep, clock=time.monotonic) -> None:
        if self.min_interval_s <= 0:
            return
        host = urlsplit(url).netloc
        with self._lock:
            now = clock()
            last = self._last.get(host)
            if last is not None:
                delta = now - last
                if delta < self.min_interval_s:
                    sleep(self.min_interval_s - delta)
                    now = clock()
            self._last[host] = now
