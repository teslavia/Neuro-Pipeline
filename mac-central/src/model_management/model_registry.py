"""Model registry for managing model lifecycle: deploy, undeploy, rollback, status."""

import logging
import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ModelStatus(Enum):
    PENDING = "pending"
    DEPLOYED = "deployed"
    FAILED = "failed"
    UNDEPLOYED = "undeployed"


@dataclass
class ModelRecord:
    model_id: str
    model_path: str
    model_type: str = "detection"
    version: str = "1.0.0"
    metadata: Dict[str, str] = field(default_factory=dict)
    status: ModelStatus = ModelStatus.PENDING
    deployed_at: float = 0.0
    target_device_id: str = ""
    npu_core: int = -1
    previous_version: Optional[str] = None
    benchmark: Optional[Dict] = None  # VLM validation benchmark results


class ModelRegistry:
    """Central registry for model lifecycle management."""

    def __init__(self, max_models_per_device: int = 3) -> None:
        self._models: Dict[str, ModelRecord] = {}
        self._lock = threading.Lock()
        self._max_models_per_device = max_models_per_device
        self._history: List[Dict] = []
        logger.info("ModelRegistry initialized (max %d models/device)", max_models_per_device)

    def deploy(self, model_id: str, model_path: str, model_type: str = "detection",
               version: str = "1.0.0", target_device_id: str = "",
               npu_core: int = -1, metadata: Optional[Dict[str, str]] = None) -> bool:
        """Deploy a model. Returns True on success."""
        with self._lock:
            if model_id in self._models and self._models[model_id].status == ModelStatus.DEPLOYED:
                logger.warning("Model %s already deployed", model_id)
                return False

            device_models = [
                m for m in self._models.values()
                if m.target_device_id == target_device_id
                and m.status == ModelStatus.DEPLOYED
            ]
            if len(device_models) >= self._max_models_per_device:
                logger.warning("Max models (%d) reached for device %s",
                               self._max_models_per_device, target_device_id)
                return False

            record = ModelRecord(
                model_id=model_id,
                model_path=model_path,
                model_type=model_type,
                version=version,
                metadata=metadata or {},
                status=ModelStatus.DEPLOYED,
                deployed_at=time.time(),
                target_device_id=target_device_id,
                npu_core=npu_core,
            )
            # Track previous version for rollback
            if model_id in self._models:
                record.previous_version = self._models[model_id].version

            self._models[model_id] = record
            self._history.append({
                "action": "deploy", "model_id": model_id,
                "version": version, "timestamp": time.time(),
            })
            logger.info("Model deployed: %s v%s -> device %s core %d",
                        model_id, version, target_device_id or "all", npu_core)
            return True

    def undeploy(self, model_id: str) -> bool:
        """Undeploy a model. Returns True on success."""
        with self._lock:
            if model_id not in self._models:
                logger.warning("Model %s not found", model_id)
                return False
            record = self._models[model_id]
            record.status = ModelStatus.UNDEPLOYED
            self._history.append({
                "action": "undeploy", "model_id": model_id,
                "timestamp": time.time(),
            })
            logger.info("Model undeployed: %s", model_id)
            return True

    def rollback(self, model_id: str) -> bool:
        """Rollback to previous version. Returns True on success."""
        with self._lock:
            if model_id not in self._models:
                return False
            record = self._models[model_id]
            if not record.previous_version:
                logger.warning("No previous version for %s", model_id)
                return False
            old_version = record.version
            record.version = record.previous_version
            record.previous_version = old_version
            record.deployed_at = time.time()
            record.status = ModelStatus.DEPLOYED
            self._history.append({
                "action": "rollback", "model_id": model_id,
                "from_version": old_version,
                "to_version": record.version,
                "timestamp": time.time(),
            })
            logger.info("Model rolled back: %s %s -> %s", model_id, old_version, record.version)
            return True

    def get_model(self, model_id: str) -> Optional[ModelRecord]:
        with self._lock:
            return self._models.get(model_id)

    def list_models(self, device_id: str = "", status: Optional[ModelStatus] = None) -> List[ModelRecord]:
        """List models, optionally filtered by device and/or status."""
        with self._lock:
            models = list(self._models.values())
        if device_id:
            models = [m for m in models if m.target_device_id == device_id]
        if status is not None:
            models = [m for m in models if m.status == status]
        return models

    def model_count(self, device_id: str = "") -> int:
        with self._lock:
            if device_id:
                return sum(1 for m in self._models.values()
                           if m.target_device_id == device_id
                           and m.status == ModelStatus.DEPLOYED)
            return sum(1 for m in self._models.values()
                       if m.status == ModelStatus.DEPLOYED)
