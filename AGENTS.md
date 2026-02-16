# Developer Agent Guide (AGENTS.md)

This document provides essential technical context for AI agents (and humans) working on the **Neuro-Pipeline** project.

## 1. Project Context
Neuro-Pipeline is a heterogeneous AI inference system:
- **RK3588 Edge**: C++17 application for real-time video processing (V4L2/MPP/RGA) and NPU inference (RKNN).
- **Mac Central**: Python 3.10+ application for LLM/VLM orchestration (MLX) on Apple Silicon.
- **Communication**: Bidirectional gRPC streams using Protobuf definitions in `proto/`.

---

## 2. Build & Test Commands

### RK3588 Edge (C++)
- **Build from scratch**:
  ```bash
  cd rk3588-edge && mkdir -p build && cd build
  cmake .. -DUSE_MOCK_HAL=ON  # Use mock for development on non-RK3588
  make -j$(nproc)
  ```
- **Cross-Compile for ARM64**:
  ```bash
  cmake .. -DCMAKE_TOOLCHAIN_FILE=../cmake/aarch64-toolchain.cmake -DUSE_MOCK_HAL=OFF
  make -j$(nproc)
  ```
- **Run Unit Tests**: `cd build && ./run_unit_tests`
- **Run Integration Tests**: `cd build && ./run_integration_tests` (requires hardware or mocks enabled)
- **Run Single Test**: `./run_unit_tests --gtest_filter=MemoryPoolTest.AllocSuccess`
- **Check All**: `cd build && make check`
- **Format Code**: `clang-format -i src/**/*.cpp include/**/*.hpp`
- **Clean**: `rm -rf build/*`

### Mac Central (Python)
- **Environment Setup**: 
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  pip install -e ".[dev]"
  ```
- **Run All Tests**: `pytest mac-central/tests`
- **Run Single Test**: `pytest mac-central/tests/unit/test_mlx.py -k test_generate_text`
- **Protobuf Generation**: `python3 tools/generate_proto.py`
- **Linting & Formatting**:
  - `black mac-central` (Follows 100 char limit)
  - `isort mac-central` (Group by standard, third-party, local)
  - `flake8 mac-central` (Basic linting)
  - `mypy mac-central` (Strict typing - MUST PASS)

---

## 3. Code Style Guidelines

### General Principles
- **Heterogeneity**: Code must be optimized for the specific hardware (NPU/UMA).
- **Zero-Copy**: Data passing between V4L2 -> MPP -> RGA -> RKNN must use DMA-BUF file descriptors. Avoid `memcpy` at all costs in the data path.
- **Async First**: Communication and long-running inference tasks should never block the main pipeline.

### C++ Standards (Google + High Performance)
- **Standard**: C++17. No exceptions.
- **Indentation**: 2 spaces. No tabs.
- **Naming Conventions**:
    - **Classes/Structs**: `PascalCase` (e.g., `MemoryManager`).
    - **Methods/Functions**: `PascalCase` (e.g., `AllocateBuffer()`).
    - **Variables**: `snake_case` (e.g., `buffer_size`).
    - **Constants/Enums**: `kPascalCase` (e.g., `kMaxBufferSize`).
    - **Private Members**: `snake_case_` (e.g., `context_`).
    - **Files**: `snake_case.cpp` / `snake_case.hpp`.
- **Memory Management**: 
    - Use `std::unique_ptr` for ownership.
    - Use `std::shared_ptr` only for shared data buffers in the pipeline.
    - Avoid `new` / `delete`.
- **Hardware Abstraction**: 
    - Use **PIMPL (Pointer to Implementation)** to hide hardware-specific SDKs (RKNN, MPP) from public headers.
- **Error Handling**: 
    - Use `bool` or `std::optional<T>` for performance-critical paths.
    - Use `std::error_code` for system-level errors.
    - Exceptions are allowed only in non-critical setup code.

### Python Standards
- **Formatting**: Strictly follow `black` and `isort`.
- **Typing**: **Strict Type Hints are mandatory**.
    - Every function must have types for all arguments and return values.
    - Use `typing.Annotated` for complex metadata if needed.
- **Naming Conventions**:
    - **Classes**: `PascalCase`.
    - **Functions/Variables**: `snake_case`.
    - **Constants**: `UPPER_SNAKE_CASE`.
- **Docstrings**: Google-style docstrings for all public classes and functions.
- **Concurrency**: Use `asyncio` for the gRPC server and orchestration logic.
- **Model Integration**: Use `mlx` for Apple Silicon. Ensure models are loaded with appropriate quantization (e.g., 4-bit).

---

## 4. Key Directories & Components

- `proto/`: Central Protobuf definitions. The "Source of Truth" for the interface.
- `rk3588-edge/src/hal/`: Hardware Layer. V4L2 camera, MPP decoding, RGA scaling, RTSP source.
- `rk3588-edge/src/ai_inference/`: NPU Logic. RKNN context management, post-processing, NPU scheduler.
- `rk3588-edge/src/app/`: Pipeline coordinator, video recorder, edge main.
- `mac-central/src/llm_vlm/`: Central AI. MLX inference engine and prompt engineering.
- `mac-central/src/communication/`: gRPC server, rate limiter.
- `mac-central/src/observability/`: Metrics, tracing, alerting, circuit breaker, retry.
- `mac-central/src/storage/`: SQLite persistence, cloud storage.
- `extensions/dashboard/`: FastAPI + htmx monitoring UI (HTTP Basic Auth).
- `docs/ARCHITECTURE.md`: Technical deep-dive into the zero-copy pipeline.

---

## 5. Agent Instructions & Rules

- **API Changes**: If you modify `proto/*.proto`, you **MUST** run `python3 tools/generate_proto.py` and ensure both C++ and Python sides still compile.
- **Testing**:
    - Add unit tests for every new feature in `tests/`.
    - Use GoogleTest (C++) and pytest (Python).
- **Performance**:
    - Always check for unnecessary copies in C++ code.
    - Use `NEON` intrinsics for CPU-bound image operations if RGA is not applicable.
- **Concurrency Safety**:
    - C++: Use `std::mutex` or lock-free queues for data passing between threads.
    - Python: Avoid blocking the `asyncio` event loop with heavy CPU tasks; use `run_in_executor` if necessary.
- **Documentation**: Update `docs/API_REFERENCE.md` if gRPC services are added or changed.
- **Git**: Use atomic commits. Follow the pattern: `feat(edge): add RGA scaling`, `fix(central): resolve MLX OOM`.

---

## 6. Common Pitfalls
- **Memory Leaks**: RKNN and MPP require explicit memory release. Ensure PIMPL destructors call the appropriate SDK `release` or `destroy` functions.
- **DMA-BUF Fds**: Always close file descriptors after they are no longer needed to avoid running out of FDs.
- **Protobuf Versions**: Ensure `protoc` version matches the runtime libraries in both environments.
