#!/usr/bin/env bash
#
# Cross-compile Neuro-Pipeline edge binary for RK3588 (aarch64)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RK3588_DIR="${REPO_ROOT}/rk3588-edge"
BUILD_DIR="${RK3588_DIR}/build"
TOOLCHAIN_FILE="${RK3588_DIR}/cmake/aarch64-toolchain.cmake"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo "============================================"
echo "  Neuro-Pipeline RK3588 Cross-Compilation"
echo "============================================"

# Check toolchain
if ! command -v aarch64-linux-gnu-gcc &> /dev/null; then
  log_error "aarch64-linux-gnu-gcc not found."
  log_info "Install via: sudo apt install gcc-aarch64-linux-gnu g++-aarch64-linux-gnu"
  log_info "Or use Docker: docker build -t np-builder ${SCRIPT_DIR} && docker run -v ${REPO_ROOT}:/workspace np-builder"
  exit 1
fi

log_info "Toolchain: $(aarch64-linux-gnu-gcc --version | head -n1)"

# Generate protobuf code first
log_info "Generating protobuf code..."
cd "${REPO_ROOT}"
python3 tools/generate_proto.py || log_warn "Protobuf generation had issues"

# Create build directory
mkdir -p "${BUILD_DIR}"
cd "${BUILD_DIR}"

# CMake configure
log_info "Running CMake..."
cmake "${RK3588_DIR}" \
  -DCMAKE_TOOLCHAIN_FILE="${TOOLCHAIN_FILE}" \
  -DCMAKE_BUILD_TYPE="${BUILD_TYPE:-Release}" \
  -DBUILD_TESTING="${BUILD_TESTING:-OFF}"

# Build
log_info "Building ($(nproc) threads)..."
make -j"$(nproc)"

log_info "Build complete!"
log_info "Binary: ${BUILD_DIR}/neuro_pipeline_edge"
log_info ""
log_info "Deploy to RK3588:"
log_info "  scp ${BUILD_DIR}/neuro_pipeline_edge root@<rk3588-ip>:/usr/local/bin/"
