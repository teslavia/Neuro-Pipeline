"""Custom exception hierarchy for Neuro-Pipeline."""


class NeuroPipelineError(Exception):
    """Base exception for all Neuro-Pipeline errors."""


class ConfigError(NeuroPipelineError):
    """Configuration validation or loading error."""


class ModelLoadError(NeuroPipelineError):
    """Model loading or initialization error."""


class InferenceError(NeuroPipelineError):
    """Inference execution error."""


class StorageError(NeuroPipelineError):
    """Database or cloud storage operation error."""


class CommunicationError(NeuroPipelineError):
    """gRPC or network communication error."""
