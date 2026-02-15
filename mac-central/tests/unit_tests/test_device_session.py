"""Tests for DeviceSessionManager."""

import time
import pytest

from src.communication.device_session import DeviceSession, DeviceSessionManager


class TestDeviceSession:
    def test_default_session(self):
        s = DeviceSession(device_id="edge-001")
        assert s.device_id == "edge-001"
        assert s.status == "connected"
        assert s.frames_received == 0


class TestDeviceSessionManager:
    def test_register_and_list(self):
        mgr = DeviceSessionManager()
        assert mgr.register("edge-001", device_name="Rock 5B")
        assert mgr.device_count == 1
        sessions = mgr.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].device_name == "Rock 5B"

    def test_register_duplicate_updates(self):
        mgr = DeviceSessionManager()
        mgr.register("edge-001", device_name="Old")
        mgr.register("edge-001", device_name="New")
        assert mgr.device_count == 1
        assert mgr.get_session("edge-001").device_name == "New"

    def test_max_devices_limit(self):
        mgr = DeviceSessionManager(max_devices=2)
        assert mgr.register("edge-001")
        assert mgr.register("edge-002")
        assert not mgr.register("edge-003")
        assert mgr.device_count == 2

    def test_heartbeat_updates_timestamp(self):
        mgr = DeviceSessionManager()
        mgr.register("edge-001")
        old_ts = mgr.get_session("edge-001").last_heartbeat
        time.sleep(0.01)
        mgr.heartbeat("edge-001")
        new_ts = mgr.get_session("edge-001").last_heartbeat
        assert new_ts > old_ts

    def test_increment_frames(self):
        mgr = DeviceSessionManager()
        mgr.register("edge-001")
        mgr.increment_frames("edge-001", 5)
        assert mgr.get_session("edge-001").frames_received == 5
        mgr.increment_frames("edge-001")
        assert mgr.get_session("edge-001").frames_received == 6

    def test_unregister(self):
        mgr = DeviceSessionManager()
        mgr.register("edge-001")
        mgr.unregister("edge-001")
        assert mgr.device_count == 0
        assert mgr.get_session("edge-001") is None

    def test_cleanup_expired(self):
        mgr = DeviceSessionManager(expiry_timeout=0.05)
        mgr.register("edge-001")
        mgr.register("edge-002")
        # Manually backdate one session
        mgr._sessions["edge-001"].last_heartbeat = time.time() - 1.0
        expired = mgr.cleanup_expired()
        assert "edge-001" in expired
        assert mgr.device_count == 1

    def test_stale_detection(self):
        mgr = DeviceSessionManager(heartbeat_interval=0.01, expiry_timeout=10.0)
        mgr.register("edge-001")
        mgr._sessions["edge-001"].last_heartbeat = time.time() - 0.05
        mgr.cleanup_expired()
        assert mgr.get_session("edge-001").status == "stale"

    def test_heartbeat_nonexistent_device(self):
        mgr = DeviceSessionManager()
        mgr.heartbeat("nonexistent")  # Should not raise

    def test_unregister_nonexistent_device(self):
        mgr = DeviceSessionManager()
        mgr.unregister("nonexistent")  # Should not raise
