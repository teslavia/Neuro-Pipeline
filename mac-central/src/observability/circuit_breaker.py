"""Three-state circuit breaker: CLOSED → OPEN → HALF_OPEN → CLOSED."""

import time


class CircuitBreaker:
    """Protects a downstream call from repeated failures."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max: int = 1,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max

        self.state: str = "closed"
        self._failure_count: int = 0
        self._last_failure_time: float = 0.0
        self._half_open_calls: int = 0

    def allow_request(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                self.state = "half_open"
                self._half_open_calls = 1
                return True
            return False
        # half_open
        if self._half_open_calls < self.half_open_max:
            self._half_open_calls += 1
            return True
        return False

    def record_success(self) -> None:
        if self.state == "half_open":
            self.state = "closed"
        self._failure_count = 0
        self._half_open_calls = 0

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self.state == "half_open":
            self.state = "open"
        elif self._failure_count >= self.failure_threshold:
            self.state = "open"
