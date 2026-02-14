# Neuro-Pipeline KPI Report

Version: v1.0.0 | Date: 2026-02-14 | Platform: RK3588 Edge + Mac Mini M-series Central

## 1. Edge Device (RK3588) Performance

| Metric | Target | Measured | Status |
|--------|--------|----------|--------|
| Video capture FPS | >= 25 | 28.5 | PASS |
| YOLO inference latency | < 30ms | 20.3ms | PASS |
| NPU utilization | > 60% | 72% | PASS |
| End-to-end frame latency | < 50ms | 35.1ms | PASS |
| Memory usage (RSS) | < 512MB | ~280MB | PASS |
| CPU usage (8-core) | < 40% | ~25% | PASS |

### Edge Pipeline Breakdown

```
V4L2 capture:   3.2ms
MPP decode:     2.1ms (hardware)
RGA resize:     1.5ms (hardware)
RKNN inference: 20.3ms (NPU)
YOLO postproc:  2.8ms (CPU)
gRPC send:      5.2ms
─────────────────────────
Total:          35.1ms (~28.5 FPS)
```

## 2. Central Server (Mac Mini Apple Silicon) Performance

### MLX Inference — Llama-3.2-3B-Instruct 4-bit Quantized

| Metric | Value |
|--------|-------|
| Model size (disk) | 1.7 GB |
| Model load time | 755ms |
| Short generation (30 tokens) | 326ms |
| Medium generation (100 tokens) | 976ms |
| Long generation (200 tokens) | 1,872ms |
| Throughput | ~100 tok/s |
| Memory (UMA) | ~2.1 GB |

### Quantization Impact

| Format | Size | Load Time | Throughput |
|--------|------|-----------|------------|
| HuggingFace FP16 | 6.4 GB | N/A (incompatible) | N/A |
| MLX 4-bit | 1.7 GB | 755ms | ~100 tok/s |

## 3. gRPC Communication

| Metric | Value |
|--------|-------|
| Unary RPC latency (LAN) | ~5ms |
| Bidirectional stream setup | ~12ms |
| Detection result payload | ~200 bytes |
| Frame + detection payload | ~150 KB (JPEG) |
| Max message size | 16 MB |
| Reconnection time | < 2s |

## 4. End-to-End Pipeline

```
Edge capture → Edge inference → gRPC → Central MLX → Response
   3.2ms        20.3ms          5ms     976ms         5ms
                                                    ─────────
                                        Total:      ~1,010ms
```

| Metric | Value |
|--------|-------|
| Detection-only (no VLM) | ~35ms |
| Detection + VLM analysis | ~1,010ms |
| VLM trigger rate | Configurable per-rule |

## 5. Test Coverage

| Component | Tests | Status |
|-----------|-------|--------|
| C++ Edge (mock HAL) | 146 | All passing |
| Python Central | 93 | All passing (3 VLM skipped without model) |
| gRPC integration | 24 | All passing |
| MLX real inference | 5 | All passing |

## 6. Resource Summary

| Resource | Edge (RK3588) | Central (Mac Mini) |
|----------|---------------|-------------------|
| CPU | 8-core ARM A76/A55 | Apple M-series |
| RAM | 16 GB LPDDR5 | 16+ GB UMA |
| Accelerator | 6 TOPS NPU | Apple GPU/ANE |
| Storage | 63 GB NVMe | 256+ GB SSD |
| Model size | 8.5 MB (RKNN) | 1.7 GB (MLX 4-bit) |

## 7. Observability Metrics

| Metric | Value |
|--------|-------|
| Prometheus endpoint | :9090/metrics |
| Health probes | /healthz (liveness), /readyz (readiness) |
| Circuit breaker threshold | 5 failures |
| Circuit breaker recovery | 30s |
| Alert webhook cooldown | 60s |

### Metrics Exposed

- Counters: `detections_total`, `vlm_requests_total`, `grpc_errors_total`
- Histograms: `inference_duration_seconds`, `vlm_queue_time_seconds`
- Gauges: `vlm_queue_size`, `circuit_breaker_state`
