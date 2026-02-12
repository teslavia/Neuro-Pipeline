FROM debian:bookworm AS base

# Avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install base tools + cross-compilation toolchain in one layer
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    wget \
    curl \
    python3 \
    python3-pip \
    pkg-config \
    libssl-dev \
    gcc-aarch64-linux-gnu \
    g++-aarch64-linux-gnu \
    binutils-aarch64-linux-gnu \
    && rm -rf /var/lib/apt/lists/*

# Install protobuf and gRPC
RUN apt-get update && apt-get install -y \
    protobuf-compiler \
    libprotobuf-dev \
    libgrpc++-dev \
    libgrpc-dev \
    protobuf-compiler-grpc \
    && rm -rf /var/lib/apt/lists/*

# Install Python gRPC tools
RUN pip3 install --break-system-packages grpcio-tools

# ── RK3588 Sysroot ───────────────────────────────────────────────
# Copy pre-assembled sysroot (run prepare_sysroot.sh first)
# Contains RKNN, MPP, RGA headers and aarch64 libraries
COPY sysroot/ /opt/rk3588-sysroot/

# Create workspace
WORKDIR /workspace

# Cross-compiler environment
ENV CC=aarch64-linux-gnu-gcc
ENV CXX=aarch64-linux-gnu-g++
ENV AR=aarch64-linux-gnu-ar
ENV RANLIB=aarch64-linux-gnu-ranlib
ENV SYSROOT=/opt/rk3588-sysroot

# Marker so scripts can detect they're inside the container
ENV IN_DOCKER=1

CMD ["/bin/bash"]
