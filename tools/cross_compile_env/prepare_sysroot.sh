#!/usr/bin/env bash
#
# Assemble RK3588 sysroot from local RKSDK for cross-compilation.
#
# This script extracts RKNN, MPP, and RGA headers/libraries from the
# local RKSDK mirror and organizes them into a sysroot directory
# that can be copied into the Docker cross-compile container.
#
# Usage:
#   bash tools/cross_compile_env/prepare_sysroot.sh [RKSDK_DIR]
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSROOT_DIR="${SCRIPT_DIR}/sysroot"

# Default RKSDK path — override via argument or environment variable
RKSDK_DIR="${1:-${RKSDK_DIR:-/Volumes/TMAC/Satoshi/DEV/mac/github/RKSDK}}"
RKNPU2_DIR="${RKSDK_DIR}/rknn-toolkit2/rknpu2"
THIRDPARTY_DIR="${RKNPU2_DIR}/examples/3rdparty"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo "============================================"
echo "  RK3588 Sysroot Assembly"
echo "============================================"

# ── Validate RKSDK paths ──────────────────────────────────────────
if [ ! -d "${RKNPU2_DIR}" ]; then
    log_error "RKSDK not found at: ${RKNPU2_DIR}"
    log_info  "Set RKSDK_DIR or pass as argument: $0 /path/to/RKSDK"
    exit 1
fi

RKNN_INCLUDE="${RKNPU2_DIR}/runtime/Linux/librknn_api/include"
RKNN_LIB="${RKNPU2_DIR}/runtime/Linux/librknn_api/aarch64"
MPP_INCLUDE="${THIRDPARTY_DIR}/mpp/include/rockchip"
MPP_LIB="${THIRDPARTY_DIR}/mpp/Linux/aarch64"
RGA_INCLUDE="${THIRDPARTY_DIR}/rga/include"
RGA_LIB="${THIRDPARTY_DIR}/rga/libs/Linux/gcc-aarch64"

for dir in "${RKNN_INCLUDE}" "${RKNN_LIB}" "${MPP_INCLUDE}" "${MPP_LIB}" "${RGA_INCLUDE}" "${RGA_LIB}"; do
    if [ ! -d "${dir}" ]; then
        log_error "Required directory not found: ${dir}"
        exit 1
    fi
done

log_info "RKSDK: ${RKSDK_DIR}"

# ── Clean and create sysroot structure ────────────────────────────
if [ -d "${SYSROOT_DIR}" ]; then
    log_warn "Removing existing sysroot: ${SYSROOT_DIR}"
    rm -rf "${SYSROOT_DIR}"
fi

mkdir -p "${SYSROOT_DIR}/usr/include/rockchip"
mkdir -p "${SYSROOT_DIR}/usr/include/rga"
mkdir -p "${SYSROOT_DIR}/usr/lib"

# ── Copy RKNN Runtime ─────────────────────────────────────────────
log_info "Copying RKNN headers..."
cp -v "${RKNN_INCLUDE}"/rknn_api.h        "${SYSROOT_DIR}/usr/include/"
cp -v "${RKNN_INCLUDE}"/rknn_matmul_api.h "${SYSROOT_DIR}/usr/include/" 2>/dev/null || true
cp -v "${RKNN_INCLUDE}"/rknn_custom_op.h  "${SYSROOT_DIR}/usr/include/" 2>/dev/null || true

log_info "Copying RKNN library..."
cp -v "${RKNN_LIB}"/librknnrt.so "${SYSROOT_DIR}/usr/lib/"

# ── Copy MPP (Media Process Platform) ────────────────────────────
log_info "Copying MPP headers..."
cp -v "${MPP_INCLUDE}"/*.h "${SYSROOT_DIR}/usr/include/rockchip/"

log_info "Copying MPP libraries..."
# On macOS, git may store ELF symlinks as broken files. The real binary is .so.0
# Copy the actual ELF binary, then create proper symlinks.
if [ -f "${MPP_LIB}/librockchip_mpp.so.0" ]; then
    cp -v "${MPP_LIB}/librockchip_mpp.so.0" "${SYSROOT_DIR}/usr/lib/"
    ln -sfv librockchip_mpp.so.0 "${SYSROOT_DIR}/usr/lib/librockchip_mpp.so.1"
    ln -sfv librockchip_mpp.so.0 "${SYSROOT_DIR}/usr/lib/librockchip_mpp.so"
elif [ -f "${MPP_LIB}/librockchip_mpp.so" ] && file "${MPP_LIB}/librockchip_mpp.so" | grep -q ELF; then
    cp -v "${MPP_LIB}/librockchip_mpp.so" "${SYSROOT_DIR}/usr/lib/"
else
    log_error "No valid librockchip_mpp.so binary found in ${MPP_LIB}"
    exit 1
fi

# ── Copy RGA (Raster Graphic Acceleration) ────────────────────────
log_info "Copying RGA headers..."
cp -v "${RGA_INCLUDE}"/*.h "${SYSROOT_DIR}/usr/include/rga/"
# Also copy im2d.hpp if present
cp -v "${RGA_INCLUDE}"/*.hpp "${SYSROOT_DIR}/usr/include/rga/" 2>/dev/null || true

log_info "Copying RGA libraries..."
cp -v "${RGA_LIB}"/librga.so "${SYSROOT_DIR}/usr/lib/"
cp -v "${RGA_LIB}"/librga.a  "${SYSROOT_DIR}/usr/lib/" 2>/dev/null || true

# ── Summary ───────────────────────────────────────────────────────
echo ""
echo "============================================"
echo "  Sysroot Assembly Complete"
echo "============================================"
log_info "Location: ${SYSROOT_DIR}"
echo ""
log_info "Contents:"
echo "  usr/include/"
ls -1 "${SYSROOT_DIR}/usr/include/" | sed 's/^/    /'
echo "  usr/include/rockchip/"
ls -1 "${SYSROOT_DIR}/usr/include/rockchip/" | head -5 | sed 's/^/    /'
echo "    ... ($(ls -1 "${SYSROOT_DIR}/usr/include/rockchip/" | wc -l | tr -d ' ') files)"
echo "  usr/include/rga/"
ls -1 "${SYSROOT_DIR}/usr/include/rga/" | head -5 | sed 's/^/    /'
echo "    ... ($(ls -1 "${SYSROOT_DIR}/usr/include/rga/" | wc -l | tr -d ' ') files)"
echo "  usr/lib/"
ls -1 "${SYSROOT_DIR}/usr/lib/" | sed 's/^/    /'

TOTAL_SIZE=$(du -sh "${SYSROOT_DIR}" | cut -f1)
log_info "Total sysroot size: ${TOTAL_SIZE}"
echo ""
log_info "Next step: build Docker image or run build_rk3588.sh"
