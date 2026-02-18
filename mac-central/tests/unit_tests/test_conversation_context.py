"""Tests for ConversationContext."""

import pytest

from src.inference.mlx_llm_inference import ConversationContext, MLXInferenceEngine
from pathlib import Path


class TestConversationContext:
    def test_empty_context(self):
        ctx = ConversationContext()
        assert ctx.turn_count == 0
        prompt = ctx.build_prompt("Hello")
        assert prompt == "User: Hello"

    def test_add_turns(self):
        ctx = ConversationContext()
        ctx.add_turn("user", "What do you see?")
        ctx.add_turn("assistant", "I see a person walking.")
        assert ctx.turn_count == 1
        prompt = ctx.build_prompt("Is the person running?")
        assert "What do you see?" in prompt
        assert "I see a person walking." in prompt
        assert "Is the person running?" in prompt

    def test_max_turns_truncation(self):
        ctx = ConversationContext(max_turns=2)
        for i in range(10):
            ctx.add_turn("user", f"Question {i}")
            ctx.add_turn("assistant", f"Answer {i}")
        # Should keep only last 4 entries (2 turns * 2 messages)
        assert len(ctx._history) == 4

    def test_clear(self):
        ctx = ConversationContext()
        ctx.add_turn("user", "Hello")
        ctx.clear()
        assert ctx.turn_count == 0


class TestEngineConversation:
    def test_get_conversation_creates_new(self):
        engine = MLXInferenceEngine(Path("models/test"))
        ctx = engine.get_conversation("edge-001")
        assert isinstance(ctx, ConversationContext)

    def test_get_conversation_returns_same(self):
        engine = MLXInferenceEngine(Path("models/test"))
        ctx1 = engine.get_conversation("edge-001")
        ctx2 = engine.get_conversation("edge-001")
        assert ctx1 is ctx2

    def test_different_devices_different_contexts(self):
        engine = MLXInferenceEngine(Path("models/test"))
        ctx1 = engine.get_conversation("edge-001")
        ctx2 = engine.get_conversation("edge-002")
        assert ctx1 is not ctx2

    def test_clear_conversation(self):
        engine = MLXInferenceEngine(Path("models/test"))
        ctx = engine.get_conversation("edge-001")
        ctx.add_turn("user", "Hello")
        engine.clear_conversation("edge-001")
        assert ctx.turn_count == 0
