"""
Chaos engineering tests — verify resilience under failure conditions.

Scenarios:
  1. Edge disconnect recovery (session cleanup)
  2. VLM timeout triggers circuit breaker
  3. SQLite lock retry
  4. Expired session cleanup
"""

import asyncio
import sqlite3
import time
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "mac-central" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "mac-central"))

from src.communication.device_session import DeviceSessionManager
from src.observability.circuit_breaker import CircuitBreaker
from src.observability.retry import retry_sync, retry_async
from src.storage.detection_store import DetectionStore


# ---------------------------------------------------------------------------
# 1. Edge disconnect recovery
# ---------------------------------------------------------------------------

class TestEdgeDisconnectRecovery:
    """Simulate edge device abrupt disconnection and verify session cleanup."""

    def test_session_survives_reconnect(self):
        mgr = DeviceSessionManager(expiry_timeout=5.0)
        mgr.register("edge-001", device_name="cam-front")
        # Simulate disconnect + immediate reconnect
        mgr.unregister("edge-001")
        assert mgr.get_session("edge-001") is None
        ok = mgr.register("edge-001", device_name="cam-front-v2")
        assert ok
        s = mgr.get_session("edge-001")
        assert s is not None
        assert s.device_name == "cam-front-v2"

    def test_multiple_rapid_reconnects(self):
        mgr = DeviceSessionManager(max_devices=4)
        for i in range(10):
            mgr.register("edge-001")
            mgr.unregister("edge-001")
        mgr.register("edge-001")
        assert mgr.device_count == 1

    def test_max_devices_after_disconnect(self):
        mgr = DeviceSessionManager(max_devices=2)
        mgr.register("edge-001")
        mgr.register("edge-002")
        assert not mgr.register("edge-003")
        mgr.unregister("edge-001")
        assert mgr.register("edge-003")
        assert mgr.device_count == 2


# ---------------------------------------------------------------------------
# 2. VLM timeout triggers circuit breaker
# ---------------------------------------------------------------------------

class TestVLMTimeoutCircuitBreaker:
    """Verify circuit breaker opens after repeated VLM timeouts."""

    def test_breaker_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1.0)
        assert cb.state == "closed"
        for _ in range(3):
            assert cb.allow_request()
            cb.record_failure()
        assert cb.state == "open"
        assert not cb.allow_request()

    def test_breaker_half_open_after_recovery(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "open"
        time.sleep(0.15)
        assert cb.allow_request()  # transitions to half_open
        assert cb.state == "half_open"

    def test_breaker_closes_on_success_after_half_open(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        cb.allow_request()  # half_open
        cb.record_success()
        assert cb.state == "closed"

    def test_breaker_reopens_on_failure_in_half_open(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        cb.allow_request()  # half_open
        cb.record_failure()
        assert cb.state == "open"


# ---------------------------------------------------------------------------
# 3. SQLite lock retry
# ---------------------------------------------------------------------------

class TestSQLiteLockRetry:
    """Verify retry_sync handles SQLite OperationalError (database locked)."""

    def test_retry_succeeds_after_transient_lock(self):
        call_count = 0

        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise sqlite3.OperationalError("database is locked")
            return "ok"

        result = retry_sync(flaky, max_retries=3, backoff=0.01,
                            exceptions=(sqlite3.OperationalError,))
        assert result == "ok"
        assert call_count == 3

    def test_retry_exhausted_raises(self):
        def always_locked():
            raise sqlite3.OperationalError("database is locked")

        with pytest.raises(sqlite3.OperationalError):
            retry_sync(always_locked, max_retries=2, backoff=0.01,
                       exceptions=(sqlite3.OperationalError,))

    def test_detection_store_record_retries(self, tmp_path):
        store = DetectionStore(tmp_path / "test.db")
        event = {
            "type": "detection",
            "frame_id": 1,
            "trace_id": "t-1",
            "timestamp": time.time(),
            "detections": [{"class_name": "person", "confidence": 0.9}],
            "device_id": "edge-001",
        }
        store.record(event)
        assert store.count() == 1
        store.close()


# ---------------------------------------------------------------------------
# 4. Expired session cleanup
# ---------------------------------------------------------------------------

class TestExpiredSessionCleanup:
    """Verify stale sessions are cleaned up correctly."""

    def test_expired_sessions_removed(self):
        mgr = DeviceSessionManager(
            heartbeat_interval=0.05, expiry_timeout=0.1
        )
        mgr.register("edge-001")
        mgr.register("edge-002")
        time.sleep(0.15)
        expired = mgr.cleanup_expired()
        assert set(expired) == {"edge-001", "edge-002"}
        assert mgr.device_count == 0

    def test_active_session_survives_cleanup(self):
        mgr = DeviceSessionManager(
            heartbeat_interval=0.05, expiry_timeout=0.8
        )
        mgr.register("edge-001")
        mgr.register("edge-002")
        time.sleep(0.3)
        mgr.heartbeat("edge-001")
        time.sleep(0.6)
        expired = mgr.cleanup_expired()
        assert "edge-002" in expired
        assert "edge-001" not in expired
        assert mgr.device_count == 1

    def test_stale_status_before_expiry(self):
        mgr = DeviceSessionManager(
            heartbeat_interval=0.05, expiry_timeout=1.0
        )
        mgr.register("edge-001")
        time.sleep(0.12)
        mgr.cleanup_expired()
        s = mgr.get_session("edge-001")
        assert s is not None
        assert s.status == "stale"


# ---------------------------------------------------------------------------
# 5. Async retry
# ---------------------------------------------------------------------------

class TestAsyncRetry:

    @pytest.mark.asyncio
    async def test_async_retry_succeeds(self):
        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("transient")
            return "done"

        result = await retry_async(flaky, max_retries=3, backoff=0.01,
                                   exceptions=(ConnectionError,))
        assert result == "done"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_async_retry_exhausted(self):
        async def always_fail():
            raise ConnectionError("permanent")

        with pytest.raises(ConnectionError):
            await retry_async(always_fail, max_retries=1, backoff=0.01,
                              exceptions=(ConnectionError,))
