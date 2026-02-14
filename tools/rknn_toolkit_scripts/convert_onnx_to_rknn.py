#!/usr/bin/env python3
"""
ONNX → RKNN model conversion script for Neuro-Pipeline.

Usage:
    python convert_onnx_to_rknn.py --onnx yolov5s.onnx --output yolov5s.rknn
    python convert_onnx_to_rknn.py --onnx yolov5s.onnx --output yolov5s.rknn --quantize --dataset dataset.txt

Requires: rknn-toolkit2 (pip install rknn-toolkit2)
"""

import argparse
import sys
import os


def convert(args):
    try:
        from rknn.api import RKNN
    except ImportError:
        print("ERROR: rknn-toolkit2 not installed.")
        print("Install: pip install rknn-toolkit2")
        sys.exit(1)

    rknn = RKNN(verbose=args.verbose)

    # Configure preprocessing (YOLOv5 standard: normalize to [0,1])
    print(f"[1/4] Configuring model for {args.target_platform}...")
    rknn.config(
        mean_values=[[0, 0, 0]],
        std_values=[[255, 255, 255]],
        target_platform=args.target_platform,
        quantized_algorithm=args.quant_algorithm,
    )

    # Load ONNX model
    print(f"[2/4] Loading ONNX model: {args.onnx}")
    ret = rknn.load_onnx(model=args.onnx)
    if ret != 0:
        print(f"ERROR: Failed to load ONNX model (code={ret})")
        sys.exit(1)

    # Build (with optional quantization)
    do_quant = args.quantize and args.dataset
    print(f"[3/4] Building RKNN model (quantize={do_quant})...")
    ret = rknn.build(
        do_quantization=do_quant,
        dataset=args.dataset if do_quant else None,
    )
    if ret != 0:
        print(f"ERROR: Build failed (code={ret})")
        sys.exit(1)

    # Export
    print(f"[4/4] Exporting to: {args.output}")
    ret = rknn.export_rknn(args.output)
    if ret != 0:
        print(f"ERROR: Export failed (code={ret})")
        sys.exit(1)

    file_size = os.path.getsize(args.output) / (1024 * 1024)
    print(f"Done. Output: {args.output} ({file_size:.1f} MB)")

    rknn.release()


def main():
    parser = argparse.ArgumentParser(description="Convert ONNX model to RKNN")
    parser.add_argument("--onnx", required=True, help="Input ONNX model path")
    parser.add_argument("--output", required=True, help="Output RKNN model path")
    parser.add_argument("--target-platform", default="rk3588",
                        choices=["rk3588", "rk3566", "rk3568"],
                        help="Target platform (default: rk3588)")
    parser.add_argument("--quantize", action="store_true",
                        help="Enable INT8 quantization (requires --dataset)")
    parser.add_argument("--dataset", default=None,
                        help="Calibration dataset file (one image path per line)")
    parser.add_argument("--quant-algorithm", default="normal",
                        choices=["normal", "mmse"],
                        help="Quantization algorithm (default: normal)")
    parser.add_argument("--verbose", action="store_true",
                        help="Enable verbose output")
    args = parser.parse_args()

    if args.quantize and not args.dataset:
        parser.error("--quantize requires --dataset")

    convert(args)


if __name__ == "__main__":
    main()
