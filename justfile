# Neuro-Pipeline — unified build & test entry point
# Install: brew install just (macOS) / cargo install just

default:
    @just --list

# ── Proto ──────────────────────────────────────────
proto:
    python3 tools/generate_proto.py

# ── Python Tests ───────────────────────────────────
test-py:
    cd mac-central && source .venv/bin/activate && pytest tests/ -v --tb=short -o "addopts="

test-py-unit:
    cd mac-central && source .venv/bin/activate && pytest tests/unit_tests/ -v -o "addopts="

test-dashboard:
    pytest extensions/dashboard/tests/ -v -o "addopts="

test-e2e:
    pytest tests/e2e/ tests/chaos/ -v -o "addopts="

lint:
    flake8 mac-central/src/ --max-line-length=100

fmt:
    black mac-central/src/ mac-central/tests/

# ── C++ Edge ───────────────────────────────────────
build-edge mock="ON":
    cd rk3588-edge && mkdir -p build && cd build && \
    cmake .. -DUSE_MOCK_HAL={{mock}} -DBUILD_TESTING=ON && make -j$(nproc)

test-cpp:
    cd rk3588-edge/build && ctest --output-on-failure

build-docker mock="ON":
    USE_MOCK_HAL={{mock}} bash tools/cross_compile_env/build_rk3588.sh

# ── Infra ──────────────────────────────────────────
monitoring-up:
    cd infra && docker compose -f docker-compose.monitoring.yml up -d

monitoring-down:
    cd infra && docker compose -f docker-compose.monitoring.yml down

# ── Deploy ─────────────────────────────────────────
deploy:
    bash tools/deploy_rk3588.sh

# ── Aggregate ──────────────────────────────────────
test-all: test-py test-dashboard test-cpp

version:
    @python3 -c "import json; print(json.load(open('VERSION.json'))['version'])"
