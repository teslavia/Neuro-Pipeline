# Third-Party Dependencies

This directory manages all external dependencies via git submodules and project-maintained stubs.

## Submodules

| Directory | Repository | License | Purpose |
|-----------|-----------|---------|---------|
| `rknn-toolkit2/` | [airockchip/rknn-toolkit2](https://github.com/airockchip/rknn-toolkit2) | Rockchip (proprietary + Apache 2.0) | RKNN/MPP/RGA headers and aarch64 libraries for cross-compilation sysroot |
| `googletest/` | [google/googletest](https://github.com/google/googletest) v1.14.0 | BSD-3-Clause | C++ unit testing framework |

## Initialization

```bash
# Clone all submodules (shallow)
git submodule update --init --depth 1

# Clone only googletest (for C++ tests without SDK)
git submodule update --init --depth 1 third_party/googletest
```

## How They're Used

- **rknn-toolkit2**: `prepare_sysroot.sh` extracts headers and `.so` libraries from this submodule into `tools/cross_compile_env/sysroot/` for Docker cross-compilation. Fallback: local RKSDK directory.
- **googletest**: Referenced by `rk3588-edge/tests/CMakeLists.txt`. Fallback: FetchContent from GitHub.

## Stubs

`stubs/` contains minimal type-definition headers written by this project (not third-party code). They provide just enough type info for CI native builds with `USE_MOCK_HAL=ON` where the real SDK headers are not needed.
