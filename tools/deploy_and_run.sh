#!/usr/bin/env bash
#
# End-to-end: cross-compile on Mac (via Docker), deploy to RK3588, run remotely.
#
# Usage:
#   bash tools/deploy_and_run.sh [--skip-build] [--skip-deploy] [-- <remote_args>]
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONF_FILE="${SCRIPT_DIR}/rk3588_device.conf"
BUILD_DIR="${REPO_ROOT}/rk3588-edge/build"
BINARY_NAME="neuro_pipeline_edge"

SKIP_BUILD=0
SKIP_DEPLOY=0
REMOTE_ARGS=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-build)  SKIP_BUILD=1; shift ;;
        --skip-deploy) SKIP_DEPLOY=1; shift ;;
        --)            shift; REMOTE_ARGS="$*"; break ;;
        *)             REMOTE_ARGS="$*"; break ;;
    esac
done

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

# Load device config
if [ ! -f "${CONF_FILE}" ]; then
    log_error "Device config not found: ${CONF_FILE}"
    exit 1
fi
source "${CONF_FILE}"

SSH_TARGET="${RK3588_USER}@${RK3588_HOST}"
SSH_OPTS="-o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new -p ${RK3588_PORT}"

echo "============================================"
echo "  Neuro-Pipeline: Build → Deploy → Run"
echo "============================================"
echo ""

# ══════════════════════════════════════════════════════════════════
# Step 1: Cross-compile
# ══════════════════════════════════════════════════════════════════
if [ "${SKIP_BUILD}" -eq 0 ]; then
    log_step "1/3 Cross-compiling..."
    bash "${SCRIPT_DIR}/cross_compile_env/build_rk3588.sh"
else
    log_step "1/3 Skipping build (--skip-build)"
fi

# Verify binary exists
if [ ! -f "${BUILD_DIR}/${BINARY_NAME}" ]; then
    log_error "Binary not found: ${BUILD_DIR}/${BINARY_NAME}"
    log_info  "Run without --skip-build to compile first"
    exit 1
fi

log_info "Binary: $(file "${BUILD_DIR}/${BINARY_NAME}")"
log_info "Size:   $(du -h "${BUILD_DIR}/${BINARY_NAME}" | cut -f1)"

# ══════════════════════════════════════════════════════════════════
# Step 2: Deploy to device
# ══════════════════════════════════════════════════════════════════
if [ "${SKIP_DEPLOY}" -eq 0 ]; then
    log_step "2/3 Deploying to ${SSH_TARGET}..."

    # Ensure deploy directory exists
    ssh ${SSH_OPTS} "${SSH_TARGET}" "mkdir -p ${RK3588_DEPLOY_DIR}"

    # Copy binary
    scp -P "${RK3588_PORT}" "${BUILD_DIR}/${BINARY_NAME}" \
        "${SSH_TARGET}:${RK3588_DEPLOY_DIR}/${BINARY_NAME}"

    # Copy config files if they exist
    if [ -d "${REPO_ROOT}/rk3588-edge/config" ]; then
        scp -P "${RK3588_PORT}" -r "${REPO_ROOT}/rk3588-edge/config" \
            "${SSH_TARGET}:${RK3588_DEPLOY_DIR}/"
    fi

    # Make executable
    ssh ${SSH_OPTS} "${SSH_TARGET}" "chmod +x ${RK3588_DEPLOY_DIR}/${BINARY_NAME}"

    log_info "Deployed to ${RK3588_DEPLOY_DIR}/${BINARY_NAME}"
else
    log_step "2/3 Skipping deploy (--skip-deploy)"
fi

# ══════════════════════════════════════════════════════════════════
# Step 3: Run on device
# ══════════════════════════════════════════════════════════════════
log_step "3/3 Running on RK3588..."

LOG_FILE="/tmp/neuro_pipeline_$(date +%Y%m%d_%H%M%S).log"

echo ""
echo -e "${CYAN}--- Remote Output ---${NC}"

ssh ${SSH_OPTS} "${SSH_TARGET}" \
    "cd ${RK3588_DEPLOY_DIR} && ./${BINARY_NAME} ${REMOTE_ARGS} 2>&1 | tee ${LOG_FILE}"

EXIT_CODE=${PIPESTATUS[0]}

echo -e "${CYAN}--- End Remote Output ---${NC}"
echo ""

# ── Collect log ───────────────────────────────────────────────────
LOCAL_LOG_DIR="${REPO_ROOT}/tmp/device_logs"
mkdir -p "${LOCAL_LOG_DIR}"
LOCAL_LOG="${LOCAL_LOG_DIR}/$(basename "${LOG_FILE}")"

scp -P "${RK3588_PORT}" "${SSH_TARGET}:${LOG_FILE}" "${LOCAL_LOG}" 2>/dev/null && \
    log_info "Log saved: ${LOCAL_LOG}" || \
    log_warn "Could not retrieve remote log"

if [ "${EXIT_CODE}" -eq 0 ]; then
    log_info "Run completed successfully"
else
    log_error "Run failed with exit code: ${EXIT_CODE}"
fi

exit "${EXIT_CODE}"
