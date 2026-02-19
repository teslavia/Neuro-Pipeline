"""Detection processor — extracted from CentralOrchestrator.process_detection."""

import asyncio
import time
from typing import Any, List, Optional

from src.core.logging import get_logger
from src.core.event_bus import EventBus
from src.observability.metrics import detections_total, vlm_requests_total, vlm_queue_depth
from src.observability.tracing import span

logger = get_logger(__name__)


class DetectionProcessor:
    """Processes incoming detections: box extraction, rule matching, VLM enqueue,
    behavior analysis, anomaly scoring."""

    def __init__(
        self,
        event_bus: EventBus,
        vlm_queue: asyncio.Queue,
        vlm_rules=None,
        behavior_analyzer=None,
        anomaly_baseline=None,
        alert_manager=None,
        inference_engine=None,
        prompt_generator=None,
    ) -> None:
        self._event_bus = event_bus
        self._vlm_queue = vlm_queue
        self._vlm_rules = vlm_rules or []
        self._behavior_analyzer = behavior_analyzer
        self._anomaly_baseline = anomaly_baseline
        self._alert_manager = alert_manager
        self._inference_engine = inference_engine
        self._prompt_generator = prompt_generator
        self._event_count = 0
        self._shutting_down = False

    @property
    def event_count(self) -> int:
        return self._event_count

    @property
    def vlm_rules(self):
        return self._vlm_rules

    @vlm_rules.setter
    def vlm_rules(self, rules):
        self._vlm_rules = rules

    async def process(self, result: Any) -> Optional[str]:
        """Process a detection result from edge device."""
        self._event_count += 1
        trace_id = getattr(result, "trace_id", f"unknown-{self._event_count}")
        device_id = getattr(result, "device_id", "")

        with span("process_detection", {
            "trace_id": trace_id,
            "device_id": device_id,
            "frame_id": str(result.frame_id),
            "box_count": str(len(result.boxes)),
        }):
            log = logger.bind(trace_id=trace_id) if hasattr(logger, "bind") else logger
            log.info(
                f"Processing detection #{self._event_count}: "
                f"frame_id={result.frame_id}, boxes={len(result.boxes)}, device={device_id}"
            )

            detections = []
            for box in result.boxes:
                detections_total.labels(class_name=box.class_name).inc()
                detections.append({
                    "class_name": box.class_name,
                    "confidence": box.confidence,
                    "x_min": box.x_min,
                    "y_min": box.y_min,
                    "x_max": box.x_max,
                    "y_max": box.y_max,
                })

            matched_rule = self._match_vlm_rule(detections)

            if matched_rule and self._inference_engine and result.frame_data:
                prompt = self._prompt_generator.generate(
                    detections, template=matched_rule.prompt_template
                )
                if self._shutting_down:
                    logger.warning("Shutting down, rejecting VLM request")
                else:
                    try:
                        self._vlm_queue.put_nowait({
                            "frame_data": result.frame_data,
                            "prompt": prompt,
                            "frame_id": result.frame_id,
                            "trace_id": trace_id,
                            "device_id": device_id,
                            "detections": detections,
                            "rule": matched_rule.class_name,
                        })
                    except asyncio.QueueFull:
                        vlm_requests_total.labels(status="dropped").inc()
                        logger.warning("VLM queue full, dropping analysis request")
                        if self._alert_manager:
                            asyncio.create_task(
                                self._alert_manager.check_and_fire(
                                    "vlm_queue_full", {"frame_id": result.frame_id}
                                )
                            )
                vlm_queue_depth.set(self._vlm_queue.qsize())

            # Behavior analysis (v2)
            if self._behavior_analyzer and detections:
                try:
                    behavior_events = self._behavior_analyzer.analyze(
                        device_id, detections, timestamp=time.time()
                    )
                    for be in behavior_events:
                        self._event_bus.publish({
                            "type": "behavior_alert",
                            "device_id": device_id,
                            "behavior_type": be.behavior_type.value,
                            "confidence": be.confidence,
                            "description": be.description,
                            "timestamp": be.timestamp,
                        })
                except Exception as e:
                    logger.warning(f"Behavior analysis failed: {e}")

            # Anomaly scoring (v2)
            if self._anomaly_baseline and detections:
                try:
                    score = self._anomaly_baseline.score(
                        device_id, "detections_count", float(len(detections))
                    )
                    if score.is_anomaly:
                        self._event_bus.publish({
                            "type": "anomaly_alert",
                            "device_id": device_id,
                            "metric_name": "detections_count",
                            "value": score.value,
                            "z_score": score.z_score,
                            "baseline_mean": score.baseline_mean,
                            "timestamp": time.time(),
                        })
                except Exception as e:
                    logger.warning(f"Anomaly scoring failed: {e}")

            self._event_bus.publish({
                "type": "detection",
                "frame_id": result.frame_id,
                "trace_id": trace_id,
                "device_id": device_id,
                "detections": detections,
                "timestamp": time.time(),
            })
            return None

    def _match_vlm_rule(self, detections: list):
        """Check if any detection matches a VLM trigger rule."""
        for rule in self._vlm_rules:
            if any(
                d["class_name"] == rule.class_name
                and d["confidence"] > rule.min_confidence
                for d in detections
            ):
                return rule
        return None
