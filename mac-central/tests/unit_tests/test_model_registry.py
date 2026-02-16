"""Tests for ModelRegistry."""

import pytest
from src.model_management.model_registry import ModelRegistry, ModelStatus


class TestModelRegistry:
    def setup_method(self):
        self.registry = ModelRegistry(max_models_per_device=3)

    def test_deploy_model(self):
        ok = self.registry.deploy("yolov5s", "/models/yolov5s.rknn", version="1.0.0")
        assert ok is True
        record = self.registry.get_model("yolov5s")
        assert record is not None
        assert record.status == ModelStatus.DEPLOYED
        assert record.version == "1.0.0"

    def test_deploy_duplicate_fails(self):
        self.registry.deploy("yolov5s", "/models/yolov5s.rknn")
        ok = self.registry.deploy("yolov5s", "/models/yolov5s.rknn")
        assert ok is False

    def test_max_models_per_device(self):
        for i in range(3):
            assert self.registry.deploy(f"model-{i}", f"/m/{i}.rknn", target_device_id="edge-001")
        ok = self.registry.deploy("model-3", "/m/3.rknn", target_device_id="edge-001")
        assert ok is False

    def test_different_devices_independent(self):
        for i in range(3):
            self.registry.deploy(f"a-{i}", f"/m/a{i}.rknn", target_device_id="edge-001")
        ok = self.registry.deploy("b-0", "/m/b0.rknn", target_device_id="edge-002")
        assert ok is True

    def test_undeploy(self):
        self.registry.deploy("yolov5s", "/models/yolov5s.rknn")
        ok = self.registry.undeploy("yolov5s")
        assert ok is True
        record = self.registry.get_model("yolov5s")
        assert record.status == ModelStatus.UNDEPLOYED

    def test_undeploy_nonexistent(self):
        assert self.registry.undeploy("nope") is False

    def test_rollback(self):
        self.registry.deploy("yolov5s", "/models/yolov5s.rknn", version="1.0.0")
        # Undeploy first so we can redeploy with new version
        self.registry.undeploy("yolov5s")
        self.registry.deploy("yolov5s", "/models/yolov5s.rknn", version="2.0.0")
        ok = self.registry.rollback("yolov5s")
        assert ok is True
        record = self.registry.get_model("yolov5s")
        assert record.version == "1.0.0"

    def test_rollback_no_previous(self):
        self.registry.deploy("yolov5s", "/models/yolov5s.rknn", version="1.0.0")
        assert self.registry.rollback("yolov5s") is False

    def test_list_models(self):
        self.registry.deploy("a", "/a.rknn", target_device_id="edge-001")
        self.registry.deploy("b", "/b.rknn", target_device_id="edge-002")
        all_models = self.registry.list_models()
        assert len(all_models) == 2
        device_models = self.registry.list_models(device_id="edge-001")
        assert len(device_models) == 1
        assert device_models[0].model_id == "a"

    def test_model_count(self):
        self.registry.deploy("a", "/a.rknn")
        self.registry.deploy("b", "/b.rknn")
        assert self.registry.model_count() == 2
        self.registry.undeploy("a")
        assert self.registry.model_count() == 1

    def test_deploy_after_undeploy_reuses_slot(self):
        self.registry.deploy("yolov5s", "/models/yolov5s.rknn", version="1.0.0")
        self.registry.undeploy("yolov5s")
        ok = self.registry.deploy("yolov5s", "/models/yolov5s_v2.rknn", version="2.0.0")
        assert ok is True
        record = self.registry.get_model("yolov5s")
        assert record.version == "2.0.0"
        assert record.status == ModelStatus.DEPLOYED
