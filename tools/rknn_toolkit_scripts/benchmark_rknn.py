#!/usr/bin/env python3
"""
RKNN model benchmark script — measures inference latency on RK3588.

Usage (on RK3588 device):
    python benchmark_rknn.py --model yolov5s.rknn --loops 100

Usage (PC simulator via rknn-toolkit2):
    python benchmark_rknn.py --model yolov5s.rknn --loops 50 --simulator
"""

import argparse
import sys
import time
import numpy as np


def benchmark(args):
    try:
        from rknn.api import RKNN
    except ImportError:
        print("ERROR: rknn-toolkit2 not installed.")
        sys.exit(1)

    rknn = RKNN(verbose=False)

    print(f"Loading model: {args.model}")
    ret = rknn.load_rknn(args.model)
    if ret != 0:
        print(f"ERROR: Failed to load RKNN model (code={ret})")
        sys.exit(1)

    if args.simulator:
        print("Initializing simulator runtime...")
        ret = rknn.init_runtime()
    else:
        print("Initializing NPU runtime...")
        ret = rknn.init_runtime(target="rk3588")

    if ret != 0:
        print(f"ERROR: Failed to init runtime (code={ret})")
        sys.exit(1)

    # Query input shape
    sdk_version = rknn.get_sdk_version()
    print(f"SDK version: {sdk_version}")

    # Create dummy input (640x640 RGB)
    img_size = args.img_size
    dummy_input = np.random.randint(0, 255, (1, img_size, img_size, 3), dtype=np.uint8)

    # Warmup
    print(f"Warming up ({args.warmup} iterations)...")
    for _ in range(args.warmup):
        rknn.inference(inputs=[dummy_input], data_format=["nhwc"])

    # Benchmark
    print(f"Benchmarking ({args.loops} iterations)...")
    latencies = []
    for i in range(args.loops):
        t0 = time.perf_counter()
        rknn.inference(inputs=[dummy_input], data_format=["nhwc"])
        t1 = time.perf_counter()
        latencies.append((t1 - t0) * 1000)

    latencies = np.array(latencies)

    print("\n" + "=" * 50)
    print(f"Model: {args.model}")
    print(f"Input: {img_size}x{img_size} RGB")
    print(f"Iterations: {args.loops}")
    print(f"{'Metric':<20} {'Value':>10}")
    print("-" * 30)
    print(f"{'Mean latency':<20} {latencies.mean():>8.2f} ms")
    print(f"{'Median latency':<20} {np.median(latencies):>8.2f} ms")
    print(f"{'P95 latency':<20} {np.percentile(latencies, 95):>8.2f} ms")
    print(f"{'P99 latency':<20} {np.percentile(latencies, 99):>8.2f} ms")
    print(f"{'Min latency':<20} {latencies.min():>8.2f} ms")
    print(f"{'Max latency':<20} {latencies.max():>8.2f} ms")
    print(f"{'Throughput':<20} {1000.0 / latencies.mean():>8.1f} FPS")
    print("=" * 50)

    rknn.release()


def main():
    parser = argparse.ArgumentParser(description="Benchmark RKNN model")
    parser.add_argument("--model", required=True, help="RKNN model path")
    parser.add_argument("--loops", type=int, default=100,
                        help="Number of inference iterations (default: 100)")
    parser.add_argument("--warmup", type=int, default=10,
                        help="Warmup iterations (default: 10)")
    parser.add_argument("--img-size", type=int, default=640,
                        help="Input image size (default: 640)")
    parser.add_argument("--simulator", action="store_true",
                        help="Use PC simulator instead of NPU")
    args = parser.parse_args()
    benchmark(args)


if __name__ == "__main__":
    main()
