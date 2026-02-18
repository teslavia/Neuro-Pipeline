"""VLM-guided edge configuration: parse VLM results and generate control commands.

This module enables the "observe → reason → act" closed loop:
1. VLM analyzes detection events
2. VLMConfigGuide extracts actionable recommendations
3. Control commands are sent to edge devices to adjust detection parameters
"""

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ConfigAdjustmentType(Enum):
    """Types of configuration adjustments that can be made."""
    DETECTION_REGION = "detection_region"      # Adjust ROI
    SENSITIVITY = "sensitivity"                # Adjust confidence threshold
    FPS = "fps"                                # Adjust frame rate
    FOCUS_AREA = "focus_area"                  # Focus on specific area


@dataclass
class DetectionRegion:
    """Normalized detection region (0.0 - 1.0)."""
    x_min: float = 0.0
    y_min: float = 0.0
    x_max: float = 1.0
    y_max: float = 1.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "x_min": self.x_min,
            "y_min": self.y_min,
            "x_max": self.x_max,
            "y_max": self.y_max,
        }

    def clamp(self) -> "DetectionRegion":
        """Return a new region with values clamped to [0, 1]."""
        return DetectionRegion(
            x_min=max(0.0, min(1.0, self.x_min)),
            y_min=max(0.0, min(1.0, self.y_min)),
            x_max=max(0.0, min(1.0, self.x_max)),
            y_max=max(0.0, min(1.0, self.y_max)),
        )


@dataclass
class ConfigAdjustment:
    """A single configuration adjustment derived from VLM analysis."""
    adjustment_type: ConfigAdjustmentType
    reason: str
    confidence: float  # 0.0 - 1.0
    region: Optional[DetectionRegion] = None
    sensitivity_delta: float = 0.0  # -0.1 to +0.1
    fps_delta: int = 0  # -5 to +5
    target_classes: List[str] = field(default_factory=list)

    def to_command_params(self) -> Dict[str, Any]:
        """Convert to protobuf command parameters."""
        params: Dict[str, Any] = {"reason": self.reason}

        if self.adjustment_type == ConfigAdjustmentType.DETECTION_REGION:
            if self.region:
                params.update(self.region.to_dict())
        elif self.adjustment_type == ConfigAdjustmentType.SENSITIVITY:
            params["delta"] = self.sensitivity_delta
        elif self.adjustment_type == ConfigAdjustmentType.FPS:
            params["delta"] = self.fps_delta
        elif self.adjustment_type == ConfigAdjustmentType.FOCUS_AREA:
            if self.region:
                params.update(self.region.to_dict())
            params["classes"] = ",".join(self.target_classes)

        return params


@dataclass
class VLMGuidanceResult:
    """Result of parsing VLM output for configuration guidance."""
    adjustments: List[ConfigAdjustment] = field(default_factory=list)
    raw_recommendations: List[str] = field(default_factory=list)
    parsing_confidence: float = 0.0
    should_apply: bool = False  # True if adjustments are actionable


# Keywords that indicate specific adjustment types
REGION_KEYWORDS = [
    r"focus on (?:the )?(?:upper|lower|left|right|center) (?:area|region|corner|portion)",
    r"adjust (?:detection )?region",
    r"change (?:the )?(?:roi|region of interest)",
    r"ignore (?:the )?(?:upper|lower|left|right|center)",
    r"monitor (?:the )?(?:upper|lower|left|right|center)",
    r"move (?:the )?detection (?:area|zone|region)",
]

SENSITIVITY_KEYWORDS = [
    r"increase (?:detection )?sensitivity",
    r"decrease (?:detection )?sensitivity",
    r"lower (?:the )?threshold",
    r"raise (?:the )?threshold",
    r"more sensitive",
    r"less sensitive",
    r"reduce false positives",
    r"catch more detections",
]

FPS_KEYWORDS = [
    r"increase (?:frame rate|fps)",
    r"decrease (?:frame rate|fps)",
    r"higher fps",
    r"lower fps",
    r"slow (?:down )?the (?:capture|stream)",
    r"speed up (?:the )?(?:capture|stream)",
]


class VLMConfigGuide:
    """Parses VLM analysis results and generates configuration adjustments.

    This enables the closed-loop "VLM → Edge Config" feedback mechanism.
    """

    def __init__(
        self,
        min_confidence: float = 0.6,
        max_adjustments_per_result: int = 3,
        enable_region_adjustment: bool = True,
        enable_sensitivity_adjustment: bool = True,
        enable_fps_adjustment: bool = False,  # Conservative default
    ) -> None:
        self.min_confidence = min_confidence
        self.max_adjustments_per_result = max_adjustments_per_result
        self.enable_region_adjustment = enable_region_adjustment
        self.enable_sensitivity_adjustment = enable_sensitivity_adjustment
        self.enable_fps_adjustment = enable_fps_adjustment

        logger.info(
            "VLMConfigGuide initialized (min_conf=%.2f, region=%s, sensitivity=%s, fps=%s)",
            min_confidence, enable_region_adjustment,
            enable_sensitivity_adjustment, enable_fps_adjustment,
        )

    def parse_vlm_result(self, vlm_result: str, context: Optional[Dict] = None) -> VLMGuidanceResult:
        """Parse VLM analysis result and extract configuration adjustments.

        Args:
            vlm_result: The VLM's analysis text
            context: Optional context (device_id, detections, etc.)

        Returns:
            VLMGuidanceResult with extracted adjustments
        """
        result = VLMGuidanceResult()
        result.raw_recommendations = self._extract_recommendations(vlm_result)

        if not result.raw_recommendations:
            logger.debug("No actionable recommendations found in VLM result")
            return result

        for rec in result.raw_recommendations[:self.max_adjustments_per_result]:
            adjustment = self._parse_recommendation(rec, context)
            if adjustment and adjustment.confidence >= self.min_confidence:
                result.adjustments.append(adjustment)

        # Calculate overall parsing confidence
        if result.adjustments:
            result.parsing_confidence = sum(
                a.confidence for a in result.adjustments
            ) / len(result.adjustments)
            result.should_apply = True

        logger.info(
            "VLMConfigGuide: parsed %d adjustments from %d recommendations (conf=%.2f)",
            len(result.adjustments), len(result.raw_recommendations), result.parsing_confidence,
        )

        return result

    def _extract_recommendations(self, text: str) -> List[str]:
        """Extract recommendation sentences from VLM result."""
        recommendations = []

        # Look for numbered or bulleted recommendations
        patterns = [
            r"(?:recommendation|suggest|advise|should)[s]?:?\s*(.+?)(?:\n|$)",
            r"\d+\.\s*(.+?)(?:\n|$)",
            r"[-•]\s*(.+?)(?:\n|$)",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
            recommendations.extend(matches)

        # Also look for sentences with action verbs
        action_pattern = r"([A-Z][^.!?]*(?:adjust|change|modify|increase|decrease|focus|monitor|ignore)[^.!?]*[.!?])"
        action_matches = re.findall(action_pattern, text)
        recommendations.extend(action_matches)

        # Deduplicate and clean
        seen = set()
        cleaned = []
        for rec in recommendations:
            rec = rec.strip()
            if rec and rec not in seen and len(rec) > 10:
                seen.add(rec)
                cleaned.append(rec)

        return cleaned

    def _parse_recommendation(self, rec: str, context: Optional[Dict]) -> Optional[ConfigAdjustment]:
        """Parse a single recommendation into a ConfigAdjustment."""
        rec_lower = rec.lower()

        # Try to match region adjustments
        if self.enable_region_adjustment:
            for pattern in REGION_KEYWORDS:
                if re.search(pattern, rec_lower):
                    region = self._extract_region(rec_lower)
                    if region:
                        return ConfigAdjustment(
                            adjustment_type=ConfigAdjustmentType.DETECTION_REGION,
                            reason=rec[:200],
                            confidence=0.7,
                            region=region,
                        )

        # Try to match sensitivity adjustments
        if self.enable_sensitivity_adjustment:
            for pattern in SENSITIVITY_KEYWORDS:
                if re.search(pattern, rec_lower):
                    delta = self._extract_sensitivity_delta(rec_lower)
                    return ConfigAdjustment(
                        adjustment_type=ConfigAdjustmentType.SENSITIVITY,
                        reason=rec[:200],
                        confidence=0.75,
                        sensitivity_delta=delta,
                    )

        # Try to match FPS adjustments
        if self.enable_fps_adjustment:
            for pattern in FPS_KEYWORDS:
                if re.search(pattern, rec_lower):
                    delta = self._extract_fps_delta(rec_lower)
                    return ConfigAdjustment(
                        adjustment_type=ConfigAdjustmentType.FPS,
                        reason=rec[:200],
                        confidence=0.6,
                        fps_delta=delta,
                    )

        return None

    def _extract_region(self, text: str) -> Optional[DetectionRegion]:
        """Extract a detection region from text."""
        # Default to full frame
        region = DetectionRegion()

        # Check for directional keywords
        if "upper" in text or "top" in text:
            region.y_min = 0.0
            region.y_max = 0.5
        if "lower" in text or "bottom" in text:
            region.y_min = 0.5
            region.y_max = 1.0
        if "left" in text:
            region.x_min = 0.0
            region.x_max = 0.5
        if "right" in text:
            region.x_min = 0.5
            region.x_max = 1.0
        if "center" in text or "middle" in text:
            region.x_min = 0.25
            region.x_max = 0.75
            region.y_min = 0.25
            region.y_max = 0.75

        # Check if we extracted anything meaningful
        if region != DetectionRegion():
            return region.clamp()

        # Try to extract numeric coordinates
        coords = re.findall(r"(\d+(?:\.\d+)?)\s*(?:%|percent)?", text)
        if len(coords) >= 4:
            try:
                return DetectionRegion(
                    x_min=float(coords[0]) / 100,
                    y_min=float(coords[1]) / 100,
                    x_max=float(coords[2]) / 100,
                    y_max=float(coords[3]) / 100,
                ).clamp()
            except (ValueError, IndexError):
                pass

        return None

    def _extract_sensitivity_delta(self, text: str) -> float:
        """Extract sensitivity adjustment delta from text."""
        if any(w in text for w in ["increase", "higher", "more sensitive", "catch more"]):
            return 0.05  # Increase sensitivity (lower threshold)
        elif any(w in text for w in ["decrease", "lower", "less sensitive", "reduce false"]):
            return -0.05  # Decrease sensitivity (raise threshold)
        return 0.0

    def _extract_fps_delta(self, text: str) -> int:
        """Extract FPS adjustment delta from text."""
        if any(w in text for w in ["increase", "higher", "speed up", "faster"]):
            return 5
        elif any(w in text for w in ["decrease", "lower", "slow down", "slower"]):
            return -5
        return 0

    def create_control_command(
        self,
        adjustment: ConfigAdjustment,
        device_id: str,
        command_id: int,
    ) -> Dict[str, Any]:
        """Create a gRPC control command from an adjustment.

        Args:
            adjustment: The ConfigAdjustment to apply
            device_id: Target device ID
            command_id: Unique command ID

        Returns:
            Dict suitable for creating a ControlCommand protobuf
        """
        type_mapping = {
            ConfigAdjustmentType.DETECTION_REGION: 7,  # SET_DETECTION_REGION
            ConfigAdjustmentType.SENSITIVITY: 8,       # SET_SENSITIVITY
            ConfigAdjustmentType.FPS: 0,               # SET_FPS
            ConfigAdjustmentType.FOCUS_AREA: 7,        # SET_DETECTION_REGION
        }

        return {
            "type": type_mapping.get(adjustment.adjustment_type, 0),
            "command_id": command_id,
            "parameters": adjustment.to_command_params(),
            "target_device_id": device_id,
        }
