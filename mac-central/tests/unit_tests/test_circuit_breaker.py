"""Tests for circuit breaker."""

import time
import pytest
from unittest.mock import patch

from src.observability.circuit_breaker import CircuitBreaker


def test_closed_allows_requests():
    cb = CircuitBreaker(failure_threshold=3)
    assert cb.state == "closed"
    assert cb.allow_request() is True


def test_failures_open_circuit():
    cb = CircuitBreaker(failure_threshold=3)
    for _ in range(3):
        cb.record_failure()
    assert cb.state == "open"
    assert cb.allow_request() is False


def test_open_to_half_open_after_timeout():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "open"
    time.sleep(0.15)
    assert cb.allow_request() is True
    assert cb.state == "half_open"


def test_half_open_success_closes():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "open"
    time.sleep(0.06)
    cb.allow_request()  # transitions to half_open
    assert cb.state == "half_open"
    cb.record_success()
    assert cb.state == "closed"
    assert cb._failure_count == 0


def test_half_open_failure_reopens():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05)
    cb.record_failure()
    cb.record_failure()
    time.sleep(0.06)
    cb.allow_request()  # half_open
    cb.record_failure()
    assert cb.state == "open"


def test_half_open_max_calls():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05, half_open_max=1)
    cb.record_failure()
    cb.record_failure()
    time.sleep(0.06)
    assert cb.allow_request() is True  # first half_open call
    assert cb.allow_request() is False  # exceeded half_open_max


def test_success_resets_failure_count():
    cb = CircuitBreaker(failure_threshold=5)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    assert cb._failure_count == 0
    assert cb.state == "closed"
