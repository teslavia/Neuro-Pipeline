FROM ubuntu:22.04

# Avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install base tools
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    wget \
    curl \
    python3 \
    python3-pip \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install cross-compilation toolchain
RUN apt-get update && apt-get install -y \
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
RUN pip3 install grpcio-tools

# Create workspace
WORKDIR /workspace

# Cross-compiler environment
ENV CC=aarch64-linux-gnu-gcc
ENV CXX=aarch64-linux-gnu-g++
ENV AR=aarch64-linux-gnu-ar
ENV RANLIB=aarch64-linux-gnu-ranlib

# TODO: Add RK3588-specific libraries
# COPY sysroot/ /opt/rk3588-sysroot/
# ENV SYSROOT=/opt/rk3588-sysroot

CMD ["/bin/bash"]
