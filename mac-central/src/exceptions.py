"""Structured exception hierarchy for Neuro-Pipeline central server."""


class NeuroPipelineError(Exception):
    """Base exception for all Neuro-Pipeline errors."""


class ConfigError(NeuroPipelineError):
    """Configuration loading or validation error."""


class InferenceError(NeuroPipelineError):
    """MLX model loading or inference error."""


class CommunicationError(NeuroPipelineError):
    """gRPC communication error."""


class ModelNotLoadedError(InferenceError):
    """Attempted inference before model was loaded."""
