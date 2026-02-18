"""Multi-round VLM reasoning chain: observe → reason → verify."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ReasoningStep:
    step_name: str
    prompt: str
    result: str = ""
    elapsed_ms: float = 0.0
    timestamp: float = 0.0


@dataclass
class ReasoningResult:
    steps: List[ReasoningStep] = field(default_factory=list)
    final_conclusion: str = ""
    total_elapsed_ms: float = 0.0
    success: bool = False

    @property
    def observation(self) -> str:
        return self.steps[0].result if self.steps else ""

    @property
    def reasoning(self) -> str:
        return self.steps[1].result if len(self.steps) > 1 else ""

    @property
    def verification(self) -> str:
        return self.steps[2].result if len(self.steps) > 2 else ""


class ReasoningChain:
    """Three-step VLM reasoning: observe → reason → verify.

    Each step builds on the previous step's output, creating a chain
    of increasingly refined analysis.
    """

    STEP_NAMES = ["observe", "reason", "verify"]

    def __init__(self, max_steps: int = 3, timeout_per_step: float = 15.0) -> None:
        self.max_steps = min(max_steps, 3)
        self.timeout_per_step = timeout_per_step
        logger.info("ReasoningChain initialized (steps=%d, timeout=%.1fs)",
                    max_steps, timeout_per_step)

    async def execute(self, engine, frame_data: bytes,
                      detections: List[Dict[str, Any]],
                      prompt_generator=None,
                      device_id: str = "",
                      detection_store=None) -> ReasoningResult:
        """Execute the full reasoning chain.

        Args:
            engine: MLXInferenceEngine with analyze_image()
            frame_data: JPEG frame bytes
            detections: List of detection dicts
            prompt_generator: PromptGenerator for building prompts
            device_id: For conversation persistence
            detection_store: For saving reasoning steps
        """
        result = ReasoningResult()
        t0 = time.perf_counter()
        context = ""

        for i in range(self.max_steps):
            step_name = self.STEP_NAMES[i]
            prompt = self._build_step_prompt(step_name, detections, context)

            step = ReasoningStep(step_name=step_name, prompt=prompt,
                                 timestamp=time.time())
            step_t0 = time.perf_counter()

            try:
                step.result = await asyncio.wait_for(
                    engine.analyze_image(frame_data, prompt),
                    timeout=self.timeout_per_step,
                )
                step.elapsed_ms = (time.perf_counter() - step_t0) * 1000
                result.steps.append(step)
                context = step.result

                # Persist to conversation store
                if detection_store and device_id:
                    try:
                        detection_store.record_conversation(
                            device_id, "system",
                            f"[{step_name}] {prompt}",
                            context_type="reasoning",
                        )
                        detection_store.record_conversation(
                            device_id, "assistant",
                            step.result[:500],
                            context_type="reasoning",
                        )
                    except Exception as e:
                        logger.warning("Failed to persist reasoning step: %s", e)

                logger.info("Reasoning step '%s' completed in %.0fms",
                            step_name, step.elapsed_ms)

            except asyncio.TimeoutError:
                logger.warning("Reasoning step '%s' timed out after %.1fs",
                               step_name, self.timeout_per_step)
                step.result = f"[timeout after {self.timeout_per_step}s]"
                step.elapsed_ms = (time.perf_counter() - step_t0) * 1000
                result.steps.append(step)
                break
            except Exception as e:
                logger.error("Reasoning step '%s' failed: %s", step_name, e)
                step.result = f"[error: {e}]"
                step.elapsed_ms = (time.perf_counter() - step_t0) * 1000
                result.steps.append(step)
                break

        result.total_elapsed_ms = (time.perf_counter() - t0) * 1000
        result.success = len(result.steps) == self.max_steps
        result.final_conclusion = result.steps[-1].result if result.steps else ""

        logger.info("Reasoning chain %s in %.0fms (%d steps)",
                    "completed" if result.success else "partial",
                    result.total_elapsed_ms, len(result.steps))
        return result

    @staticmethod
    def _build_step_prompt(step_name: str, detections: List[Dict],
                           previous_context: str) -> str:
        det_summary = "; ".join(
            f"{d['class_name']} ({d['confidence']:.0%})" for d in detections
        ) if detections else "no objects"

        if step_name == "observe":
            return (
                f"Observe this scene carefully. Detected objects: {det_summary}. "
                "Describe exactly what you see — objects, positions, actions, "
                "and environmental context. Be factual and specific."
            )
        elif step_name == "reason":
            return (
                f"Based on this observation: \"{previous_context[:300]}\" "
                "Now reason about what is happening. What activities are taking place? "
                "Are there any safety concerns, unusual patterns, or noteworthy interactions? "
                "Explain your reasoning step by step."
            )
        elif step_name == "verify":
            return (
                f"Based on this analysis: \"{previous_context[:300]}\" "
                "Verify your conclusions. Rate confidence (high/medium/low). "
                "Identify what could be wrong with the analysis. "
                "Provide a final concise assessment with actionable recommendations."
            )
        return f"Analyze: {det_summary}"
