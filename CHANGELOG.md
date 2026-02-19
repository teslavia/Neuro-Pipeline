# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.4.1] - 2026-02-19

### Changed
- **Phase 0**: pyproject.toml unified pythonpath, Justfile test targets, conftest cleanup
- **Phase 1**: Generic dataclass config loader — replaces 190-line `.get()` chains (`src/core/config_loader.py`)
- **Phase 2**: Unified logger factory + `@safe_async` error decorator — eliminates 8 structlog fallbacks and 15 try-except blocks (`src/core/logging.py`, `src/core/error_handling.py`)
- **Phase 3**: Split `CentralOrchestrator` (503→120 lines) into `EventBus`, `DetectionProcessor`, `VLMProcessingPipeline` (`src/core/event_bus.py`, `src/pipeline/`)
- **Phase 4**: DI container with lazy subsystem init — `main.py` 427→150 lines (`src/core/container.py`)
- **Phase 5**: gRPC `ModelActionHandler` Strategy pattern — replaces 6-branch if/elif (`src/communication/model_actions.py`)
- **Phase 6**: Dashboard FastAPI DI — eliminates 14 global variables (`extensions/dashboard/services/deps.py`)
- **Phase 7**: C++ `InputSource` Strategy pattern — 18 branches→polymorphism (`input_source.hpp`, `input_source_factory.hpp`)
- **Phase 8**: C++ Config struct split — 30+ fields→4 sub-structs (`pipeline_config.hpp`)
- **Phase 9**: `DetectionStore` Facade with 3 internal repos (`_detection_repo.py`, `_timeseries_repo.py`, `_conversation_repo.py`)
- **Phase 10**: Shared test factories — reduce 143 duplicate mocks (`tests/factories.py`)

### Stats
- 39 files changed, +2071/−1567 lines
- 435 Python tests (360 unit + 20 dashboard + 26 E2E + 29 chaos), 0 failures

## [2.4.0] - 2026-02-19

### Added
- Edge JPEG frame encoding via stb_image_write (`send_frame_data` config)
- `jpeg_quality` parameter (1-100, default 70, ~30-50KB per frame)
- `jpeg_encoder.hpp` utility wrapping stbi_write_jpg_to_func
- VLM end-to-end pipeline: Edge camera → JPEG → gRPC → Central Qwen2-VL analysis

### Fixed
- Central: mlx_vlm.generate() expects file path, not PIL Image — write tempfile
- Central: Extract .text from GenerationResult return type
- Test: Relax VLM synthetic image assertion (model may return empty for trivial images)

## [2.3.1] - 2026-02-19

### Fixed
- GCC aggregate init error in DetectionQueue default param on aarch64
- Camera device path updated to /dev/video3 (1080P USB Camera)

## [2.3.0] - 2026-02-19

### Added
- Edge offline detection cache queue (`DetectionQueue`) — buffers during gRPC disconnects, auto-drains on reconnect
- Config hot-reload integration in `main.py` — live updates for logging level, VLM rules, alerting, rate limiting
- Dynamic log level REST endpoint `GET/PUT /api/v2/logging/level`
- Prometheus alert rules (6 rules: EdgeDisconnected, VLMQueueNearFull, VLMHighErrorRate, GRPCLatencyHigh, DetectionRateDrop, HighValidationErrorRate)
- Grafana SLO dashboard (8 panels: availability, latency P99, error budget, FPS, gRPC SLI)
- Grafana alerting provisioning with webhook contact point
- Justfile unified build/test entry point (`just --list`)
- VLM model validation pipeline (`VLMValidator`) with load + inference benchmarks
- Multi-VLM model support (`central.vlm_models` config, `switch_vlm_model()` runtime switching)
- Devcontainer for contributor onboarding (`.devcontainer/`)

### Changed
- `GRPCClient::StreamDetection()` now buffers on failure instead of dropping detections
- `AlertManager` gains `update_rules()` for hot-reload
- `TokenBucketRateLimiter` gains `update_limits()` for hot-reload
- `ModelRecord` extended with `benchmark` field
- Dashboard config PUT endpoint triggers `ConfigWatcher.force_reload()`
- Docker compose monitoring stack mounts Prometheus rules and Grafana alerting

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
