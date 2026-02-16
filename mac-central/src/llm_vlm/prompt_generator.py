"""
Dynamic prompt generator for VLM inference.

Constructs context-aware prompts from edge detection results
to guide VLM semantic analysis.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


# Prompt templates for different analysis scenarios
TEMPLATES = {
    "scene_analysis": (
        "Analyze the following scene. "
        "Detected objects: {detections}. "
        "Describe what is happening and identify any potential safety concerns."
    ),
    "person_behavior": (
        "A person was detected at coordinates ({x_min:.2f}, {y_min:.2f}) to "
        "({x_max:.2f}, {y_max:.2f}) in the frame with confidence {confidence:.1%}. "
        "Describe the person's likely activity and assess if there are any "
        "safety hazards in the area."
    ),
    "anomaly_detection": (
        "The following objects were detected in a monitored area: {detections}. "
        "Normal objects for this area include: {normal_objects}. "
        "Identify any anomalies or unusual patterns."
    ),
    "multi_object": (
        "Multiple objects detected:\n{detection_list}\n\n"
        "Analyze the spatial relationships between these objects and describe "
        "the overall scene context."
    ),
    # v2: Reasoning chain templates
    "reasoning_observe": (
        "Observe this scene carefully. Detected objects: {detections}. "
        "Describe exactly what you see — objects, positions, actions, "
        "and environmental context. Be factual and specific."
    ),
    "reasoning_reason": (
        "Based on this observation: \"{previous_context}\"\n"
        "Now reason about what is happening. What activities are taking place? "
        "Are there any safety concerns, unusual patterns, or noteworthy interactions? "
        "Explain your reasoning step by step."
    ),
    "reasoning_verify": (
        "Based on this analysis: \"{previous_context}\"\n"
        "Verify your conclusions. Rate confidence (high/medium/low). "
        "Identify what could be wrong with the analysis. "
        "Provide a final concise assessment with actionable recommendations."
    ),
    # v2: RAG-augmented template
    "rag_scene_analysis": (
        "Analyze the following scene. Detected objects: {detections}.\n\n"
        "Historical context from this location:\n{rag_context}\n\n"
        "Considering both the current scene and historical patterns, "
        "describe what is happening and identify any concerns."
    ),
    # v2: Edge config suggestion
    "edge_config_suggestion": (
        "Based on this analysis: \"{previous_context}\"\n"
        "Detected objects: {detections}.\n"
        "Suggest optimal edge device configuration adjustments:\n"
        "1. Detection region of interest (ROI) as normalized coordinates\n"
        "2. Confidence threshold adjustment\n"
        "3. Frame rate recommendation\n"
        "Respond in JSON format with keys: roi, threshold, fps_recommendation."
    ),
}


class PromptGenerator:
    """Generates context-aware prompts from detection results."""

    def __init__(self, default_template: str = "scene_analysis") -> None:
        self.default_template = default_template
        logger.info(f"PromptGenerator initialized with template: {default_template}")

    def generate(self, detections: list[dict[str, Any]], **kwargs) -> str:
        """
        Generate a prompt from detection results.

        Args:
            detections: List of detection dicts with keys:
                class_name, confidence, x_min, y_min, x_max, y_max.
            **kwargs: Additional template variables.

        Returns:
            Formatted prompt string.
        """
        template_name = kwargs.pop("template", self.default_template)
        template = TEMPLATES.get(template_name, TEMPLATES["scene_analysis"])

        # Format detection list
        detection_strs = []
        for d in detections:
            detection_strs.append(
                f"{d['class_name']} (conf={d['confidence']:.1%}, "
                f"bbox=[{d['x_min']:.2f},{d['y_min']:.2f},"
                f"{d['x_max']:.2f},{d['y_max']:.2f}])"
            )

        # Build template variables
        template_vars = {
            "detections": "; ".join(detection_strs),
            "detection_list": "\n".join(f"- {s}" for s in detection_strs),
            **kwargs,
        }

        # Add first detection coords if available
        if detections:
            d = detections[0]
            template_vars.update({
                "x_min": d.get("x_min", 0),
                "y_min": d.get("y_min", 0),
                "x_max": d.get("x_max", 0),
                "y_max": d.get("y_max", 0),
                "confidence": d.get("confidence", 0),
            })

        try:
            prompt = template.format(**template_vars)
        except KeyError as e:
            logger.warning(f"Missing template variable {e}, using fallback")
            prompt = TEMPLATES["scene_analysis"].format(
                detections="; ".join(detection_strs)
            )

        logger.debug(f"Generated prompt ({len(prompt)} chars): {prompt[:80]}...")
        return prompt

    @staticmethod
    def available_templates() -> list[str]:
        """Return list of available template names."""
        return list(TEMPLATES.keys())
