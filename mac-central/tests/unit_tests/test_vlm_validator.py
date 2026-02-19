"""Tests for VLM model validator."""

import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock

from src.model_management.vlm_validator import VLMValidator, ValidationResult


class TestVLMValidator:
    @pytest.mark.asyncio
    async def test_validate_nonexistent_path(self):
        validator = VLMValidator()
        result = await validator.validate("/nonexistent/model/path")
        assert not result.passed
        assert not result.load_success
        assert "does not exist" in result.errors[0]

    @pytest.mark.asyncio
    async def test_validate_stub_mode(self, tmp_path):
        """When mlx_vlm is not available, stub mode should pass."""
        model_dir = tmp_path / "test-model"
        model_dir.mkdir()
        (model_dir / "config.json").write_text("{}")

        validator = VLMValidator(min_tps=1.0)
        with patch.object(validator, "_load_model", return_value=(None, None)):
            result = await validator.validate(str(model_dir))

        assert result.load_success
        assert result.inference_success
        assert result.passed

    @pytest.mark.asyncio
    async def test_validate_load_failure(self, tmp_path):
        model_dir = tmp_path / "bad-model"
        model_dir.mkdir()

        validator = VLMValidator()
        with patch.object(validator, "_load_model", side_effect=RuntimeError("corrupt")):
            result = await validator.validate(str(model_dir))

        assert not result.passed
        assert not result.load_success
        assert "Load failed" in result.errors[0]

    @pytest.mark.asyncio
    async def test_validate_slow_load(self, tmp_path):
        model_dir = tmp_path / "slow-model"
        model_dir.mkdir()

        import time
        _real_monotonic = time.monotonic
        _call_count = [0]

        def _slow_monotonic():
            _call_count[0] += 1
            # First pair of calls (load): simulate 5s gap
            if _call_count[0] <= 2:
                return _call_count[0] * 5.0
            return _real_monotonic()

        validator = VLMValidator(max_load_time=0.001)
        with patch.object(validator, "_load_model", return_value=(MagicMock(), MagicMock())):
            with patch.object(validator, "_run_inference", return_value=100):
                with patch("src.model_management.vlm_validator.time") as mock_time:
                    mock_time.monotonic = _slow_monotonic
                    result = await validator.validate(str(model_dir))

        assert result.load_success
        has_load_warning = any("Load time" in e for e in result.errors)
        assert has_load_warning

    @pytest.mark.asyncio
    async def test_validate_low_tps(self, tmp_path):
        model_dir = tmp_path / "slow-inference"
        model_dir.mkdir()

        _call_count = [0]

        def _slow_monotonic():
            _call_count[0] += 1
            # Simulate: load takes 0s, inference takes 100s
            # calls: load_start(1)=0, load_end(2)=0, infer_start(3)=0, infer_end(4)=100
            if _call_count[0] <= 2:
                return 0.0
            if _call_count[0] == 3:
                return 0.0
            return 100.0  # 100 seconds for inference

        validator = VLMValidator(min_tps=1000.0)
        with patch.object(validator, "_load_model", return_value=(MagicMock(), MagicMock())):
            with patch.object(validator, "_run_inference", return_value=1):
                with patch("src.model_management.vlm_validator.time") as mock_time:
                    mock_time.monotonic = _slow_monotonic
                    result = await validator.validate(str(model_dir))

        assert result.inference_success
        assert not result.passed
        assert any("TPS" in e for e in result.errors)

    def test_validation_result_to_dict(self):
        result = ValidationResult(
            model_path="/test",
            load_success=True,
            load_time_seconds=1.234,
            inference_success=True,
            inference_time_seconds=2.567,
            tokens_per_second=19.45,
            passed=True,
        )
        d = result.to_dict()
        assert d["model_path"] == "/test"
        assert d["load_time_seconds"] == 1.234
        assert d["tokens_per_second"] == 19.45
        assert d["passed"] is True
