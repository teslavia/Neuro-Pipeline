"""Tests for multi-round VLM reasoning chain."""

import asyncio
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from src.llm_vlm.reasoning_chain import ReasoningChain, ReasoningResult


class MockEngine:
    """Mock inference engine that returns step-aware responses."""

    def __init__(self, responses=None):
        self._call_count = 0
        self._responses = responses or [
            "I see a person walking near a building entrance.",
            "The person appears to be loitering. This could indicate surveillance.",
            "Confidence: medium. The person may just be waiting. Recommend monitoring.",
        ]

    async def analyze_image(self, frame_data, prompt):
        idx = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        return self._responses[idx]


class TestReasoningChain:
    @pytest.mark.asyncio
    async def test_full_three_step_chain(self):
        engine = MockEngine()
        chain = ReasoningChain(max_steps=3, timeout_per_step=5.0)

        result = await chain.execute(
            engine, b"fake_frame",
            detections=[{"class_name": "person", "confidence": 0.9}],
        )

        assert result.success is True
        assert len(result.steps) == 3
        assert result.steps[0].step_name == "observe"
        assert result.steps[1].step_name == "reason"
        assert result.steps[2].step_name == "verify"
        assert "person walking" in result.observation
        assert "loitering" in result.reasoning
        assert "medium" in result.verification
        assert result.total_elapsed_ms > 0

    @pytest.mark.asyncio
    async def test_two_step_chain(self):
        engine = MockEngine()
        chain = ReasoningChain(max_steps=2)

        result = await chain.execute(engine, b"frame", detections=[])

        assert len(result.steps) == 2
        assert result.steps[0].step_name == "observe"
        assert result.steps[1].step_name == "reason"
        assert result.success is True

    @pytest.mark.asyncio
    async def test_single_step_chain(self):
        engine = MockEngine()
        chain = ReasoningChain(max_steps=1)

        result = await chain.execute(engine, b"frame", detections=[])

        assert len(result.steps) == 1
        assert result.success is True

    @pytest.mark.asyncio
    async def test_timeout_stops_chain(self):
        class SlowEngine:
            async def analyze_image(self, frame_data, prompt):
                await asyncio.sleep(10)
                return "should not reach"

        chain = ReasoningChain(max_steps=3, timeout_per_step=0.1)
        result = await chain.execute(SlowEngine(), b"frame", detections=[])

        assert result.success is False
        assert len(result.steps) == 1
        assert "timeout" in result.steps[0].result

    @pytest.mark.asyncio
    async def test_error_stops_chain(self):
        class FailEngine:
            async def analyze_image(self, frame_data, prompt):
                raise RuntimeError("GPU OOM")

        chain = ReasoningChain(max_steps=3)
        result = await chain.execute(FailEngine(), b"frame", detections=[])

        assert result.success is False
        assert len(result.steps) == 1
        assert "error" in result.steps[0].result

    @pytest.mark.asyncio
    async def test_persists_to_conversation_store(self):
        engine = MockEngine()
        store = MagicMock()
        chain = ReasoningChain(max_steps=2)

        await chain.execute(
            engine, b"frame",
            detections=[{"class_name": "car", "confidence": 0.8}],
            device_id="edge-001",
            detection_store=store,
        )

        # 2 steps × 2 calls each (system prompt + assistant response)
        assert store.record_conversation.call_count == 4

    @pytest.mark.asyncio
    async def test_step_prompts_build_on_context(self):
        prompts_seen = []

        class CapturingEngine:
            async def analyze_image(self, frame_data, prompt):
                prompts_seen.append(prompt)
                return f"response to step {len(prompts_seen)}"

        chain = ReasoningChain(max_steps=3)
        await chain.execute(
            CapturingEngine(), b"frame",
            detections=[{"class_name": "person", "confidence": 0.95}],
        )

        assert len(prompts_seen) == 3
        assert "Observe" in prompts_seen[0]
        assert "response to step 1" in prompts_seen[1]  # reason uses observe output
        assert "response to step 2" in prompts_seen[2]  # verify uses reason output

    @pytest.mark.asyncio
    async def test_elapsed_timing(self):
        engine = MockEngine()
        chain = ReasoningChain(max_steps=2)

        result = await chain.execute(engine, b"frame", detections=[])

        for step in result.steps:
            assert step.elapsed_ms >= 0
            assert step.timestamp > 0
        assert result.total_elapsed_ms >= 0
