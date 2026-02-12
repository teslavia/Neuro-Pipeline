#!/usr/bin/env bash
#
# Cross-compile Neuro-Pipeline edge binary for RK3588 (aarch64)
#
# When run outside Docker: builds the Docker image and re-invokes itself inside.
# When run inside Docker:  runs cmake + make directly.
#
# Environment variables:
#   USE_MOCK_HAL  — ON (default) to build without real SDK, OFF to link real RKNN/MPP/RGA
#   BUILD_TYPE    — Release (default), Debug, RelWithDebInfo
#   BUILD_TESTING — ON/OFF (default OFF)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RK3588_DIR="${REPO_ROOT}/rk3588-edge"
BUILD_DIR="${RK3588_DIR}/build"
TOOLCHAIN_FILE="${RK3588_DIR}/cmake/aarch64-toolchain.cmake"

DOCKER_IMAGE="neuro-pipeline-builder"
USE_MOCK_HAL="${USE_MOCK_HAL:-ON}"
BUILD_TYPE="${BUILD_TYPE:-Release}"
BUILD_TESTING="${BUILD_TESTING:-OFF}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "${CYAN}[STEP]${NC}  $1"; }

echo "============================================"
echo "  Neuro-Pipeline RK3588 Cross-Compilation"
echo "============================================"
echo ""
log_info "USE_MOCK_HAL = ${USE_MOCK_HAL}"
log_info "BUILD_TYPE   = ${BUILD_TYPE}"

# ══════════════════════════════════════════════════════════════════
# Path A: Running OUTSIDE Docker → build image & re-invoke inside
# ══════════════════════════════════════════════════════════════════
if [ "${IN_DOCKER:-}" != "1" ]; then

    # ── Check Docker availability ─────────────────────────────────
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed or not in PATH."
        log_info  "Install Docker Desktop: https://www.docker.com/products/docker-desktop"
        exit 1
    fi

    if ! docker info &> /dev/null 2>&1; then
        log_error "Docker daemon is not running. Please start Docker Desktop."
        exit 1
    fi

    log_info "Docker: $(docker --version)"

    # ── Check sysroot if using real HAL ───────────────────────────
    if [ "${USE_MOCK_HAL}" = "OFF" ]; then
        if [ ! -d "${SCRIPT_DIR}/sysroot/usr/lib" ]; then
            log_error "Sysroot not found at ${SCRIPT_DIR}/sysroot/"
            log_info  "Run: bash tools/cross_compile_env/prepare_sysroot.sh"
            exit 1
        fi
        log_info "Sysroot found: ${SCRIPT_DIR}/sysroot/"
    fi

    # ── Build Docker image ────────────────────────────────────────
    log_step "Building Docker image '${DOCKER_IMAGE}'..."

    # If mock mode and no sysroot exists, create an empty one so COPY doesn't fail
    if [ "${USE_MOCK_HAL}" = "ON" ] && [ ! -d "${SCRIPT_DIR}/sysroot" ]; then
        mkdir -p "${SCRIPT_DIR}/sysroot/usr/include"
        mkdir -p "${SCRIPT_DIR}/sysroot/usr/lib"
        log_warn "Created empty sysroot (mock HAL mode)"
    fi

    docker build -t "${DOCKER_IMAGE}" "${SCRIPT_DIR}"

    # ── Run build inside container ────────────────────────────────
    log_step "Starting cross-compilation inside Docker..."

    docker run --rm \
        -v "${REPO_ROOT}:/workspace" \
        -e USE_MOCK_HAL="${USE_MOCK_HAL}" \
        -e BUILD_TYPE="${BUILD_TYPE}" \
        -e BUILD_TESTING="${BUILD_TESTING}" \
        -e IN_DOCKER=1 \
        "${DOCKER_IMAGE}" \
        bash /workspace/tools/cross_compile_env/build_rk3588.sh

    # ── Report results ────────────────────────────────────────────
    echo ""
    echo "============================================"
    echo "  Build Complete"
    echo "============================================"
    if [ -f "${BUILD_DIR}/neuro_pipeline_edge" ]; then
        log_info "Binary: ${BUILD_DIR}/neuro_pipeline_edge"
        log_info "Size:   $(du -h "${BUILD_DIR}/neuro_pipeline_edge" | cut -f1)"
        log_info "Type:   $(file "${BUILD_DIR}/neuro_pipeline_edge")"
    else
        log_warn "Binary not found at expected path. Check build output above."
        log_info "Listing build dir:"
        ls -la "${BUILD_DIR}/" 2>/dev/null || log_warn "Build directory doesn't exist"
    fi

    exit 0
fi

# ══════════════════════════════════════════════════════════════════
# Path B: Running INSIDE Docker → execute cmake + make
# ══════════════════════════════════════════════════════════════════

log_info "Running inside Docker container"
log_info "Toolchain: $(aarch64-linux-gnu-gcc --version | head -n1)"

# Generate protobuf code first
log_step "Generating protobuf code..."
cd /workspace
python3 tools/generate_proto.py 2>/dev/null || log_warn "Protobuf generation skipped or had issues"

# Create build directory
mkdir -p "${BUILD_DIR}"
cd "${BUILD_DIR}"

# CMake configure
log_step "Running CMake..."
CMAKE_ARGS=(
    "${RK3588_DIR}"
    -DCMAKE_TOOLCHAIN_FILE="${TOOLCHAIN_FILE}"
    -DCMAKE_BUILD_TYPE="${BUILD_TYPE}"
    -DBUILD_TESTING="${BUILD_TESTING}"
    -DUSE_MOCK_HAL="${USE_MOCK_HAL}"
)

cmake "${CMAKE_ARGS[@]}"

# Build
NPROC=$(nproc)
log_step "Building (${NPROC} threads)..."
make -j"${NPROC}"

log_info "Build complete inside Docker!"
