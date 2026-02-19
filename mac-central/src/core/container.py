"""Lightweight DI container — replaces ~200 lines of procedural assembly in main.py."""

import logging
from pathlib import Path
from typing import Any, Optional

from src.config import AppConfig

logger = logging.getLogger(__name__)


class ServiceContainer:
    """Lazy-loading service container. Each subsystem is built on first access."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._services: dict[str, Any] = {}

    def get(self, name: str) -> Any:
        """Get or build a service by name."""
        if name not in self._services:
            builder = getattr(self, f"_build_{name}", None)
            if builder is None:
                raise KeyError(f"Unknown service: {name}")
            self._services[name] = builder()
        return self._services[name]

    # -- Builders --

    def _build_store(self):
        from src.storage.detection_store import DetectionStore
        cfg = self._config.storage
        db_path = Path(cfg.db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return DetectionStore(db_path, retention_days=cfg.retention_days)

    def _build_session_manager(self):
        from src.communication.device_session import DeviceSessionManager
        cfg = self._config.sessions
        return DeviceSessionManager(
            max_devices=cfg.max_devices,
            expiry_timeout=cfg.expiry_timeout,
        )

    def _build_circuit_breaker(self):
        from src.observability.circuit_breaker import CircuitBreaker
        cfg = self._config.circuit_breaker
        return CircuitBreaker(
            failure_threshold=cfg.failure_threshold,
            recovery_timeout=cfg.recovery_timeout,
            half_open_max=cfg.half_open_max,
        )

    def _build_alert_manager(self):
        if not self._config.alerting.enabled:
            return None
        from src.observability.alerting import AlertManager, AlertRule, AlertSeverity, AlertRoute
        cfg = self._config.alerting
        rules = [AlertRule(name=r.name, cooldown_seconds=r.cooldown_seconds) for r in cfg.rules]
        routes = []
        for rt in cfg.routes:
            sev = rt.severity
            routes.append(AlertRoute(
                severity=AlertSeverity(sev) if isinstance(sev, str) else sev,
                webhook_url=rt.webhook_url,
            ))
        return AlertManager(
            rules=rules,
            webhook_url=cfg.webhook_url,
            routes=routes if routes else None,
        )

    def _build_cloud_storage(self):
        if not self._config.cloud_storage.enabled:
            return None
        from src.storage.cloud_storage import CloudStorageClient
        cfg = self._config.cloud_storage
        return CloudStorageClient(
            bucket=cfg.bucket,
            prefix=cfg.prefix,
            endpoint_url=cfg.endpoint_url,
            region=cfg.region,
        )

    def _build_behavior_analyzer(self):
        from src.pipeline.behavior_analyzer import BehaviorAnalyzer
        return BehaviorAnalyzer(detection_store=self.get("store"))

    def _build_reasoning_chain(self):
        if not self._config.reasoning.enabled:
            return None
        from src.inference.reasoning_chain import ReasoningChain
        cfg = self._config.reasoning
        logger.info(f"Reasoning chain: {cfg.max_steps} steps, {cfg.timeout_per_step}s/step")
        return ReasoningChain(max_steps=cfg.max_steps, timeout_per_step=cfg.timeout_per_step)

    def _build_rag_retriever(self):
        if not self._config.rag.enabled:
            return None
        from src.inference.rag_retriever import RAGRetriever
        cfg = self._config.rag
        logger.info(f"RAG retriever: {cfg.max_history_items} items, {cfg.time_window_hours}h window")
        return RAGRetriever(
            detection_store=self.get("store"),
            max_items=cfg.max_history_items,
            time_window_hours=cfg.time_window_hours,
        )

    def _build_anomaly_baseline(self):
        if not self._config.anomaly.enabled:
            return None
        from src.pipeline.anomaly_baseline import AnomalyBaseline
        cfg = self._config.anomaly
        logger.info(f"Anomaly baseline: z>{cfg.z_score_threshold}, window={cfg.baseline_window_hours}h")
        return AnomalyBaseline(
            detection_store=self.get("store"),
            baseline_window_hours=cfg.baseline_window_hours,
            z_score_threshold=cfg.z_score_threshold,
            min_samples=cfg.min_samples,
        )

    def _build_reid_engine(self):
        if not self._config.reid.enabled:
            return None
        from src.analytics.reid_engine import ReIDEngine
        cfg = self._config.reid
        logger.info(f"ReID engine: threshold={cfg.similarity_threshold}")
        return ReIDEngine(
            similarity_threshold=cfg.similarity_threshold,
            time_window_seconds=cfg.time_window_seconds,
        )

    def _build_timeseries_engine(self):
        if not self._config.timeseries.enabled:
            return None
        from src.analytics.timeseries_engine import TimeSeriesEngine
        logger.info(f"Time series engine: interval={self._config.timeseries.aggregation_interval}s")
        return TimeSeriesEngine(detection_store=self.get("store"))

    def _build_auto_annotator(self):
        if not self._config.auto_annotator.enabled:
            return None
        from src.analytics.auto_annotator import AutoAnnotator
        cfg = self._config.auto_annotator
        logger.info(f"Auto annotator: min_confidence={cfg.min_confidence}")
        return AutoAnnotator(detection_store=self.get("store"), min_confidence=cfg.min_confidence)

    def _build_report_generator(self):
        if not self._config.reporting.enabled:
            return None
        from src.analytics.report_generator import ReportGenerator
        logger.info(f"Report generator: schedule={self._config.reporting.schedule_hours}h")
        return ReportGenerator(
            detection_store=self.get("store"),
            cloud_storage=self.get("cloud_storage"),
        )

    def _build_rate_limiter(self):
        if not self._config.rate_limiting.enabled:
            return None
        from src.communication.rate_limiter import TokenBucketRateLimiter
        cfg = self._config.rate_limiting
        logger.info(f"Rate limiting: {cfg.max_rps} rps, burst {cfg.burst}")
        return TokenBucketRateLimiter(max_per_sec=cfg.max_rps, burst=cfg.burst)

    def _build_model_registry(self):
        if not self._config.model_management.enabled:
            return None
        from src.model_management.model_registry import ModelRegistry
        cfg = self._config.model_management
        logger.info(f"Model management: max {cfg.max_models_per_device} models/device")
        return ModelRegistry(max_models_per_device=cfg.max_models_per_device)

    def _build_ab_test_manager(self):
        if not self._config.ab_test.enabled:
            return None
        from src.model_management.ab_test_manager import ABTestManager
        cfg = self._config.ab_test
        logger.info(f"A/B testing: split={cfg.traffic_split}, metric={cfg.metric}")
        return ABTestManager(
            traffic_split=cfg.traffic_split,
            min_samples=cfg.min_samples,
            metric=cfg.metric,
        )

    def _build_orchestrator(self):
        from src.pipeline.central_orchestrator import CentralOrchestrator, VLMTriggerRule
        cfg = self._config
        vlm_rules = [
            VLMTriggerRule(
                class_name=r.class_name,
                min_confidence=r.min_confidence,
                prompt_template=r.prompt_template,
            )
            for r in cfg.vlm_rules
        ]
        vlm_model_path = Path(cfg.central.vlm_model_path) if cfg.central.vlm_model_path else None
        return CentralOrchestrator(
            Path(cfg.central.model_path),
            vlm_rules=vlm_rules,
            detection_store=self.get("store"),
            inference_mode=cfg.central.inference_mode,
            vlm_model_path=vlm_model_path,
            circuit_breaker=self.get("circuit_breaker"),
            alert_manager=self.get("alert_manager"),
            cloud_storage=self.get("cloud_storage"),
            batch_config=cfg.batch,
            behavior_analyzer=self.get("behavior_analyzer"),
            reasoning_chain=self.get("reasoning_chain"),
            rag_retriever=self.get("rag_retriever"),
            anomaly_baseline=self.get("anomaly_baseline"),
        )

    def _build_grpc_server(self):
        from src.communication.grpc_server import NeuroPipelineServer
        cfg = self._config
        return NeuroPipelineServer(
            cfg.central.host, cfg.central.port,
            self.get("orchestrator"),
            max_message_size_mb=cfg.central.max_message_size_mb,
            tls_config=cfg.tls if cfg.tls.enabled else None,
            session_manager=self.get("session_manager"),
            rate_limiter=self.get("rate_limiter"),
            model_registry=self.get("model_registry"),
            detection_store=self.get("store"),
            ab_test_manager=self.get("ab_test_manager"),
        )
