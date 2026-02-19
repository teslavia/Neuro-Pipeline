"""Token bucket rate limiter for gRPC streams — per-device isolation."""

import time
import threading
from typing import Dict


class TokenBucketRateLimiter:
    """Per-device token bucket rate limiter.

    Each device gets its own bucket with `burst` tokens max,
    refilling at `max_per_sec` tokens/second.
    """

    def __init__(self, max_per_sec: float = 100.0, burst: int = 20) -> None:
        self.max_per_sec = max_per_sec
        self.burst = burst
        self._buckets: Dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def allow(self, device_id: str = "") -> bool:
        """Check if a request from device_id is allowed. Consumes one token."""
        key = device_id or "__global__"
        with self._lock:
            if key not in self._buckets:
                self._buckets[key] = _Bucket(self.burst, self.max_per_sec)
            return self._buckets[key].consume()

    def update_limits(self, max_per_sec: float, burst: int) -> None:
        """Update rate limits. New limits apply to new buckets; existing buckets
        are cleared so they pick up the new values on next request."""
        with self._lock:
            self.max_per_sec = max_per_sec
            self.burst = burst
            self._buckets.clear()


class _Bucket:
    """Single token bucket."""

    def __init__(self, burst: int, refill_rate: float) -> None:
        self.burst = burst
        self.refill_rate = refill_rate
        self.tokens = float(burst)
        self.last_refill = time.monotonic()

    def consume(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.burst, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False
