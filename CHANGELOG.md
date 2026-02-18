# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.2] - 2026-02-18

### Changed
- Refactored C++ headers under unified `neuro::` namespace
- Reorganized header file structure in `include/neuro/`

### Fixed
- V4L2: Use `device_caps` when `V4L2_CAP_DEVICE_CAPS` is set

## [2.2.1] - 2026-02-17

### Added
- Dashboard integration with real analysis data for v2 Intelligence APIs
- BehaviorAnalyzer, AnomalyBaseline, RAGRetriever real-time queries

### Changed
- Removed demo data fallback from Intelligence API endpoints

## [2.2.0] - 2026-02-16

### Added
- VLM-guided configuration suggestions via `/api/v2/vlm/guidance`
- Automatic threshold adjustment recommendations based on detection patterns
- New control commands: `SET_DETECTION_REGION`, `SET_SENSITIVITY`

### Changed
- Unified version management with VERSION.json + core/version.py

## [2.1.0] - 2026-02-15

### Added
- Model cascade inference (lightweight pre-filter + heavyweight refinement)
- V2 API modular package structure with separate routers

### Changed
- Refactored dashboard into modular package (status, models, config, intelligence, tracking)
- Renamed directories for clarity: `application_logic` → `pipeline`, `llm_vlm` → `inference`

## [2.0.0] - 2026-02-14

### Added
- **Multi-Model Dynamic Switching**: Load YOLOv5s/v5m/v8s simultaneously on NPU cores 0/1/2
- **NPU 3-Core Scheduling**: `MultiModelManager` and `MultiModelScheduler` for independent core management
- **Temporal Tracker v2**: IoU-based cross-frame tracking with unique `track_id` assignment
- **Adaptive FPS Controller**: Dynamic 5–30 FPS based on detection density
- **Behavior Analyzer**: Detect loitering, running, lingering, and crowd behaviors
- **Anomaly Baseline**: Z-score anomaly detection with automatic baseline learning
- **Reasoning Chain**: Three-step inference (Observe → Reason → Verify)
- **RAG Retriever**: Historical context retrieval for enhanced inference
- **Model Registry**: Model version management and metadata storage
- **A/B Test Manager**: Traffic splitting and metric collection for model comparison
- **Time Series Engine**: Metric ingestion, aggregation, and query
- **Auto Annotator**: High-confidence sample collection for labeling
- **ReID Engine**: Cross-camera re-identification
- **Report Generator**: Scheduled summary reports
- **Plugin System**: Event bus for extensibility

### Changed
- Protobuf v2 extensions: `DetectionResult.model_id`, `DetectionResult.feature_vector`, `BoundingBox.track_id`
- New gRPC methods: `ManageModel`, `QueryTimeSeries`
- New command types: `SWITCH_MODEL_VARIANT`

### Fixed
- TemporalTracker segfault: Snapshot tracks size before matching loop
- ConfigManager multi-line list item parsing
- ConfigManager nested YAML parsing and NumOutputs field

## [1.3.0] - 2026-02-16

### Added
- Token bucket rate limiting per device
- Protobuf input validation (device_id, confidence, coordinates)
- Dashboard HTTP Basic Auth
- Session cleanup scheduling
- Control command audit logging
- OTel span instrumentation on hot paths

### Changed
- Activated dead code: RTSP source, video recorder, memory pool guards, NPU scheduler

### Fixed
- Database composite index on (device_id, timestamp)

## [1.2.0] - 2026-02-16

### Added
- Custom exception hierarchy (NeuroPipelineError + 5 subtypes)
- Config validation (ports, confidence bounds, timeouts, TLS files)
- Graceful shutdown with VLM queue drain
- Edge Prometheus metrics (C++)
- NPU 3-core scheduling (round-robin)
- RTSP source HAL module
- Event-triggered video recorder with ring buffer
- SQLite atomic backup
- Alert severity routing (INFO/WARNING/CRITICAL)

## [1.1.0] - 2026-02-16

### Added
- Multi-camera round-robin capture
- Multi-edge device sessions with heartbeat/expiry
- Model hot-swap via RELOAD_MODEL command
- VLM batch inference accumulator
- Cloud storage integration (S3/MinIO)
- Distributed tracing (OpenTelemetry)
- Structured logging (C++)
- Grafana monitoring stack (8 panels)
- Dashboard multi-device view

### Changed
- 250 total Python tests (unit + integration + chaos)

## [1.0.0] - 2026-02-14

### Added
- Prometheus metrics export
- Health probes (/healthz, /readyz)
- Circuit breaker for VLM inference
- Retry patterns with exponential backoff
- Alerting with webhook support

## [0.5.0] - 2026-02-14

### Added
- SQLite persistence with thread-safe wrapper
- Dual-mode inference engine (LLM/VLM)
- Async VLM queue
- mTLS security
- Edge frame skip configuration

## [0.4.0] - 2026-02-13

### Added
- 4-bit MLX model quantization
- FastAPI + htmx dashboard
- Config-driven VLM rules

## [0.3.0] - 2026-02-12

### Added
- Bidirectional gRPC streaming
- MLX inference engine (stub mode)

## [0.2.0] - 2026-02-11

### Added
- V4L2 camera capture
- MPP hardware decoder
- RGA image processor
- RKNN NPU inference
- Zero-copy DMA-BUF pipeline
- 28.5 FPS @ 1080p

## [0.1.0] - 2026-02-10

### Added
- CMake build system
- Docker cross-compile toolchain
- 8 core modules
- 101 initial tests
