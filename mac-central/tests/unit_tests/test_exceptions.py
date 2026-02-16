"""Tests for custom exception hierarchy."""

from src.exceptions import (
    NeuroPipelineError,
    ConfigError,
    ModelLoadError,
    InferenceError,
    StorageError,
    CommunicationError,
)


class TestExceptionHierarchy:
    def test_all_inherit_from_base(self):
        for exc_cls in (ConfigError, ModelLoadError, InferenceError,
                        StorageError, CommunicationError):
            assert issubclass(exc_cls, NeuroPipelineError)
            assert issubclass(exc_cls, Exception)

    def test_base_is_exception(self):
        assert issubclass(NeuroPipelineError, Exception)

    def test_isinstance_check(self):
        err = ConfigError("bad port")
        assert isinstance(err, NeuroPipelineError)
        assert isinstance(err, Exception)
        assert not isinstance(err, StorageError)

    def test_message_propagation(self):
        err = ModelLoadError("model not found: /tmp/foo.rknn")
        assert "model not found" in str(err)

    def test_raise_and_catch_base(self):
        try:
            raise InferenceError("timeout")
        except NeuroPipelineError as e:
            assert "timeout" in str(e)
