"""Inference module for Neuro-Pipeline central server.

Provides MLX-based LLM/VLM inference:
- mlx_llm_inference: Dual-mode MLX engine (LLM text / VLM multimodal)
- prompt_generator: Prompt templates for VLM analysis
- rag_retriever: Historical context retrieval for RAG
- reasoning_chain: Multi-round reasoning chains
- vlm_config_guide: VLM-guided edge configuration
"""

from .mlx_llm_inference import MLXInferenceEngine, ConversationContext
from .prompt_generator import PromptGenerator
from .rag_retriever import RAGRetriever, RAGContext
from .reasoning_chain import ReasoningChain, ReasoningStep, ReasoningResult
from .vlm_config_guide import (
    VLMConfigGuide,
    VLMGuidanceResult,
    ConfigAdjustment,
    ConfigAdjustmentType,
    DetectionRegion,
)

__all__ = [
    # MLX Inference
    "MLXInferenceEngine",
    "ConversationContext",
    # Prompt Generator
    "PromptGenerator",
    # RAG Retriever
    "RAGRetriever",
    "RAGContext",
    # Reasoning Chain
    "ReasoningChain",
    "ReasoningStep",
    "ReasoningResult",
    # VLM Config Guide
    "VLMConfigGuide",
    "VLMGuidanceResult",
    "ConfigAdjustment",
    "ConfigAdjustmentType",
    "DetectionRegion",
]
