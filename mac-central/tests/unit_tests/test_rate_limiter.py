"""Tests for TokenBucketRateLimiter."""

import time
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from communication.rate_limiter import TokenBucketRateLimiter


def test_within_limit_allows():
    """Requests within rate limit should be allowed."""
    rl = TokenBucketRateLimiter(max_per_sec=10, burst=5)
    for _ in range(5):
        assert rl.allow("dev-1") is True


def test_exceeds_limit_rejects():
    """Requests exceeding burst should be rejected."""
    rl = TokenBucketRateLimiter(max_per_sec=10, burst=3)
    for _ in range(3):
        rl.allow("dev-1")
    assert rl.allow("dev-1") is False


def test_burst_capacity():
    """Burst should allow initial spike up to burst size."""
    rl = TokenBucketRateLimiter(max_per_sec=1, burst=10)
    allowed = sum(1 for _ in range(15) if rl.allow("dev-1"))
    assert allowed == 10


def test_token_recovery():
    """Tokens should recover over time."""
    rl = TokenBucketRateLimiter(max_per_sec=100, burst=2)
    assert rl.allow("dev-1") is True
    assert rl.allow("dev-1") is True
    assert rl.allow("dev-1") is False
    time.sleep(0.05)  # 100 tokens/sec * 0.05s = 5 tokens recovered
    assert rl.allow("dev-1") is True


def test_device_isolation():
    """Different devices should have independent buckets."""
    rl = TokenBucketRateLimiter(max_per_sec=10, burst=2)
    assert rl.allow("dev-a") is True
    assert rl.allow("dev-a") is True
    assert rl.allow("dev-a") is False
    # dev-b should still have tokens
    assert rl.allow("dev-b") is True
