"""Multi-edge device session management."""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DeviceSession:
    """Represents a connected edge device."""

    device_id: str
    device_name: str = ""
    firmware_version: str = ""
    capabilities: List[str] = field(default_factory=list)
    connected_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    frames_received: int = 0
    status: str = "connected"  # connected, stale, disconnected
    ab_test_group: str = ""  # "control" or "treatment"
    model_version: str = ""


class DeviceSessionManager:
    """Manages edge device sessions with heartbeat tracking and expiry."""

    def __init__(
        self,
        heartbeat_interval: float = 10.0,
        expiry_timeout: float = 30.0,
        max_devices: int = 16,
    ) -> None:
        self._sessions: Dict[str, DeviceSession] = {}
        self._lock = threading.Lock()
        self.heartbeat_interval = heartbeat_interval
        self.expiry_timeout = expiry_timeout
        self.max_devices = max_devices

    def register(
        self,
        device_id: str,
        device_name: str = "",
        firmware_version: str = "",
        capabilities: Optional[List[str]] = None,
    ) -> bool:
        """Register a new device session. Returns False if max_devices reached."""
        with self._lock:
            if device_id in self._sessions:
                # Re-register: update and reset heartbeat
                s = self._sessions[device_id]
                s.last_heartbeat = time.time()
                s.status = "connected"
                if device_name:
                    s.device_name = device_name
                if firmware_version:
                    s.firmware_version = firmware_version
                if capabilities:
                    s.capabilities = capabilities
                logger.info(f"Device re-registered: {device_id}")
                return True
            if len(self._sessions) >= self.max_devices:
                logger.warning(f"Max devices ({self.max_devices}) reached, rejecting {device_id}")
                return False
            self._sessions[device_id] = DeviceSession(
                device_id=device_id,
                device_name=device_name,
                firmware_version=firmware_version,
                capabilities=capabilities or [],
            )
            logger.info(f"Device registered: {device_id}")
            return True

    def heartbeat(self, device_id: str) -> None:
        """Update heartbeat timestamp for a device."""
        with self._lock:
            if device_id in self._sessions:
                self._sessions[device_id].last_heartbeat = time.time()
                self._sessions[device_id].status = "connected"

    def increment_frames(self, device_id: str, count: int = 1) -> None:
        """Increment frame counter for a device."""
        with self._lock:
            if device_id in self._sessions:
                self._sessions[device_id].frames_received += count

    def unregister(self, device_id: str) -> None:
        """Remove a device session."""
        with self._lock:
            if device_id in self._sessions:
                del self._sessions[device_id]
                logger.info(f"Device unregistered: {device_id}")

    def cleanup_expired(self) -> List[str]:
        """Remove sessions that haven't sent a heartbeat within expiry_timeout.
        Returns list of expired device_ids."""
        now = time.time()
        expired = []
        with self._lock:
            for did, session in list(self._sessions.items()):
                if now - session.last_heartbeat > self.expiry_timeout:
                    expired.append(did)
                    del self._sessions[did]
                    logger.info(f"Device expired: {did}")
                elif now - session.last_heartbeat > self.heartbeat_interval * 2:
                    session.status = "stale"
        return expired

    def get_session(self, device_id: str) -> Optional[DeviceSession]:
        """Get a device session by ID."""
        with self._lock:
            return self._sessions.get(device_id)

    def list_sessions(self) -> List[DeviceSession]:
        """List all active device sessions."""
        with self._lock:
            return list(self._sessions.values())

    @property
    def device_count(self) -> int:
        with self._lock:
            return len(self._sessions)
