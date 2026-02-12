#!/usr/bin/env bash
#
# Deploy RK3588 SDK (RKNN runtime, MPP, RGA) to device via SSH.
#
# This script:
#   1. Checks SSH connectivity to the RK3588 device
#   2. Collects system information
#   3. Checks NPU driver status
#   4. Deploys RKNN/MPP/RGA shared libraries
#   5. Runs ldconfig and verifies deployment
#   6. Outputs a readiness report
#
# Usage:
#   bash tools/deploy_rk3588.sh [--dry-run]
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONF_FILE="${SCRIPT_DIR}/rk3588_device.conf"
SYSROOT_DIR="${SCRIPT_DIR}/cross_compile_env/sysroot"
RKSDK_DIR="${RKSDK_DIR:-/Volumes/TMAC/Satoshi/DEV/mac/github/RKSDK}"
RKNPU2_DIR="${RKSDK_DIR}/rknn-toolkit2/rknpu2"

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=1
fi

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "${CYAN}[STEP]${NC}  $1"; }
log_ok()    { echo -e "${GREEN}[  OK]${NC}  $1"; }
log_fail()  { echo -e "${RED}[FAIL]${NC}  $1"; }

# ── Load device config ────────────────────────────────────────────
if [ ! -f "${CONF_FILE}" ]; then
    log_error "Device config not found: ${CONF_FILE}"
    exit 1
fi
source "${CONF_FILE}"

SSH_TARGET="${RK3588_USER}@${RK3588_HOST}"
SSH_OPTS="-o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new -p ${RK3588_PORT}"

run_ssh() {
    if [ "${DRY_RUN}" -eq 1 ]; then
        echo "[DRY-RUN] ssh ${SSH_OPTS} ${SSH_TARGET} \"$*\""
        return 0
    fi
    ssh ${SSH_OPTS} "${SSH_TARGET}" "$@"
}

run_scp() {
    if [ "${DRY_RUN}" -eq 1 ]; then
        echo "[DRY-RUN] scp -P ${RK3588_PORT} $*"
        return 0
    fi
    scp -P "${RK3588_PORT}" -o ConnectTimeout=10 "$@"
}

echo "============================================"
echo "  RK3588 Device SDK Deployment"
echo "============================================"
echo ""
log_info "Target: ${SSH_TARGET}:${RK3588_PORT}"
log_info "Deploy dir: ${RK3588_DEPLOY_DIR}"
if [ "${DRY_RUN}" -eq 1 ]; then
    log_warn "DRY-RUN mode — no changes will be made"
fi
echo ""

# Track overall status
REPORT=()
report_add() {
    REPORT+=("$1")
}

# ══════════════════════════════════════════════════════════════════
# Step 1: Connectivity Check
# ══════════════════════════════════════════════════════════════════
log_step "1/6 Checking SSH connectivity..."

if [ "${DRY_RUN}" -eq 0 ]; then
    if ssh ${SSH_OPTS} "${SSH_TARGET}" "echo ok" &>/dev/null; then
        log_ok "SSH connection successful"
        report_add "SSH: OK"
    else
        log_fail "Cannot connect to ${SSH_TARGET}"
        log_info "Check: network, SSH service, credentials"
        exit 1
    fi
else
    echo "[DRY-RUN] ssh ${SSH_OPTS} ${SSH_TARGET} echo ok"
    report_add "SSH: DRY-RUN"
fi

# ══════════════════════════════════════════════════════════════════
# Step 2: System Information
# ══════════════════════════════════════════════════════════════════
log_step "2/6 Collecting system information..."

if [ "${DRY_RUN}" -eq 0 ]; then
    echo ""
    echo -e "${BOLD}--- System Info ---${NC}"
    run_ssh "uname -a"
    echo ""
    echo "CPU:"
    run_ssh "grep -c processor /proc/cpuinfo" | xargs -I{} echo "  {} cores"
    run_ssh "grep 'model name' /proc/cpuinfo | head -1" | sed 's/^/  /'
    echo "Memory:"
    run_ssh "free -h | head -2"
    echo "Disk:"
    run_ssh "df -h / | tail -1"
    echo ""
    report_add "System info: collected"
else
    run_ssh "uname -a && free -h && df -h /"
    report_add "System info: DRY-RUN"
fi

# ══════════════════════════════════════════════════════════════════
# Step 3: NPU Driver Check
# ══════════════════════════════════════════════════════════════════
log_step "3/6 Checking NPU driver..."

if [ "${DRY_RUN}" -eq 0 ]; then
    NPU_VERSION=$(run_ssh "sudo cat /sys/kernel/debug/rknpu/version 2>/dev/null || echo 'NOT_FOUND'")
    if [ "${NPU_VERSION}" != "NOT_FOUND" ]; then
        log_ok "NPU driver version: ${NPU_VERSION}"
        report_add "NPU driver: ${NPU_VERSION}"
    else
        # Try alternative: check /dev/rknpu device node
        NPU_DEV=$(run_ssh "ls -la /dev/rknpu* 2>/dev/null || echo 'NOT_FOUND'")
        if [ "${NPU_DEV}" != "NOT_FOUND" ] && [ -n "${NPU_DEV}" ]; then
            log_ok "NPU device node found"
            echo "  ${NPU_DEV}"
            report_add "NPU driver: detected (/dev/rknpu exists)"
        else
            log_warn "NPU driver not detected — may need kernel update"
            report_add "NPU driver: NOT FOUND"
        fi
    fi

    # Check NPU load
    NPU_LOAD=$(run_ssh "sudo cat /sys/kernel/debug/rknpu/load 2>/dev/null || echo 'N/A'")
    if [ "${NPU_LOAD}" != "N/A" ]; then
        log_info "NPU load: ${NPU_LOAD}"
    fi
else
    run_ssh "cat /sys/kernel/debug/rknpu/version; cat /sys/kernel/debug/rknpu/load"
    report_add "NPU driver: DRY-RUN"
fi

# ══════════════════════════════════════════════════════════════════
# Step 4: Deploy RKNN Runtime
# ══════════════════════════════════════════════════════════════════
log_step "4/6 Deploying RKNN runtime..."

# Determine library source: prefer sysroot, fall back to RKSDK
RKNN_LIB=""
if [ -f "${SYSROOT_DIR}/usr/lib/librknnrt.so" ]; then
    RKNN_LIB="${SYSROOT_DIR}/usr/lib/librknnrt.so"
elif [ -f "${RKNPU2_DIR}/runtime/Linux/librknn_api/aarch64/librknnrt.so" ]; then
    RKNN_LIB="${RKNPU2_DIR}/runtime/Linux/librknn_api/aarch64/librknnrt.so"
fi

if [ -n "${RKNN_LIB}" ]; then
    log_info "Source: ${RKNN_LIB}"
    run_scp "${RKNN_LIB}" "${SSH_TARGET}:/tmp/librknnrt.so"
    run_ssh "sudo cp /tmp/librknnrt.so /usr/lib/ && sudo chmod 755 /usr/lib/librknnrt.so"
    log_ok "librknnrt.so deployed"
    report_add "RKNN runtime: deployed"
else
    log_warn "librknnrt.so not found — skipping"
    log_info "Run prepare_sysroot.sh or check RKSDK_DIR"
    report_add "RKNN runtime: SKIPPED (not found)"
fi

# Deploy rknn_server if available
RKNN_SERVER="${RKNPU2_DIR}/runtime/Linux/rknn_server/aarch64/usr/bin/rknn_server"
if [ -f "${RKNN_SERVER}" ]; then
    log_info "Deploying rknn_server..."
    run_ssh "sudo killall rknn_server 2>/dev/null || true"
    run_scp "${RKNN_SERVER}" "${SSH_TARGET}:/tmp/rknn_server"
    run_ssh "sudo cp /tmp/rknn_server /usr/bin/ && sudo chmod 755 /usr/bin/rknn_server"
    log_ok "rknn_server deployed"
    report_add "rknn_server: deployed"
else
    log_info "rknn_server not found in SDK — skipping (optional)"
    report_add "rknn_server: not available"
fi

# ══════════════════════════════════════════════════════════════════
# Step 5: Deploy MPP & RGA Libraries
# ══════════════════════════════════════════════════════════════════
log_step "5/6 Deploying MPP and RGA libraries..."

# MPP
MPP_LIB=""
if [ -f "${SYSROOT_DIR}/usr/lib/librockchip_mpp.so" ]; then
    MPP_LIB="${SYSROOT_DIR}/usr/lib/librockchip_mpp.so"
elif [ -f "${RKNPU2_DIR}/examples/3rdparty/mpp/Linux/aarch64/librockchip_mpp.so" ]; then
    MPP_LIB="${RKNPU2_DIR}/examples/3rdparty/mpp/Linux/aarch64/librockchip_mpp.so"
fi

if [ -n "${MPP_LIB}" ]; then
    run_scp "${MPP_LIB}" "${SSH_TARGET}:/tmp/librockchip_mpp.so"
    run_ssh "sudo cp /tmp/librockchip_mpp.so /usr/lib/ && sudo chmod 755 /usr/lib/librockchip_mpp.so"
    log_ok "librockchip_mpp.so deployed"
    report_add "MPP library: deployed"
else
    log_warn "librockchip_mpp.so not found — skipping"
    report_add "MPP library: SKIPPED"
fi

# RGA
RGA_LIB=""
if [ -f "${SYSROOT_DIR}/usr/lib/librga.so" ]; then
    RGA_LIB="${SYSROOT_DIR}/usr/lib/librga.so"
elif [ -f "${RKNPU2_DIR}/examples/3rdparty/rga/libs/Linux/gcc-aarch64/librga.so" ]; then
    RGA_LIB="${RKNPU2_DIR}/examples/3rdparty/rga/libs/Linux/gcc-aarch64/librga.so"
fi

if [ -n "${RGA_LIB}" ]; then
    run_scp "${RGA_LIB}" "${SSH_TARGET}:/tmp/librga.so"
    run_ssh "sudo cp /tmp/librga.so /usr/lib/ && sudo chmod 755 /usr/lib/librga.so"
    log_ok "librga.so deployed"
    report_add "RGA library: deployed"
else
    log_warn "librga.so not found — skipping"
    report_add "RGA library: SKIPPED"
fi

# Run ldconfig
log_info "Running ldconfig..."
run_ssh "sudo ldconfig"

# ══════════════════════════════════════════════════════════════════
# Step 6: Verify Deployment
# ══════════════════════════════════════════════════════════════════
log_step "6/6 Verifying deployment..."

if [ "${DRY_RUN}" -eq 0 ]; then
    echo ""
    echo -e "${BOLD}--- Library Verification ---${NC}"
    for lib in librknnrt.so librockchip_mpp.so librga.so; do
        FOUND=$(run_ssh "sudo ldconfig -p | grep ${lib} || echo 'NOT_FOUND'")
        if [ "${FOUND}" != "NOT_FOUND" ] && [ -n "${FOUND}" ]; then
            log_ok "${lib} — linked"
        else
            log_fail "${lib} — not found in ldconfig"
        fi
    done

    # Create deploy directory
    run_ssh "sudo mkdir -p ${RK3588_DEPLOY_DIR} && sudo chown ${RK3588_USER}:${RK3588_USER} ${RK3588_DEPLOY_DIR}"
    log_ok "Deploy directory created: ${RK3588_DEPLOY_DIR}"
    report_add "Deploy dir: ready"
fi

# ══════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════
echo ""
echo "============================================"
echo "  Deployment Report"
echo "============================================"
for item in "${REPORT[@]}"; do
    echo "  ${item}"
done
echo ""
log_info "Device: ${SSH_TARGET}"
log_info "Deploy path: ${RK3588_DEPLOY_DIR}"
echo ""
log_info "Next: bash tools/deploy_and_run.sh"
