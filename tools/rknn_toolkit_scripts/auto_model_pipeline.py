#!/usr/bin/env python3
"""
End-to-end model conversion pipeline: .pt → .onnx → .rknn

Usage:
    python auto_model_pipeline.py --weights yolov5s.pt --output yolov5s.rknn
    python auto_model_pipeline.py --weights yolov5s.pt --output yolov5s.rknn --quantize --dataset dataset.txt
"""

import argparse
import os
import subprocess
import sys
import tempfile


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def run_step(description, cmd):
    print(f"\n{'='*60}")
    print(f"  {description}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        print(f"FAILED: {description}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Full model conversion pipeline")
    parser.add_argument("--weights", required=True, help="Input .pt model")
    parser.add_argument("--output", required=True, help="Output .rknn model")
    parser.add_argument("--img-size", type=int, default=640)
    parser.add_argument("--target-platform", default="rk3588")
    parser.add_argument("--quantize", action="store_true")
    parser.add_argument("--dataset", default=None)
    parser.add_argument("--simplify", action="store_true", default=True)
    args = parser.parse_args()

    # Intermediate ONNX path
    onnx_path = os.path.splitext(args.output)[0] + ".onnx"

    # Step 1: PT → ONNX
    pt_to_onnx = [
        sys.executable, os.path.join(SCRIPT_DIR, "convert_pt_to_onnx.py"),
        "--weights", args.weights,
        "--output", onnx_path,
        "--img-size", str(args.img_size),
    ]
    if args.simplify:
        pt_to_onnx.append("--simplify")
    run_step("Step 1: PyTorch → ONNX", pt_to_onnx)

    # Step 2: ONNX → RKNN
    onnx_to_rknn = [
        sys.executable, os.path.join(SCRIPT_DIR, "convert_onnx_to_rknn.py"),
        "--onnx", onnx_path,
        "--output", args.output,
        "--target-platform", args.target_platform,
    ]
    if args.quantize:
        onnx_to_rknn.extend(["--quantize", "--dataset", args.dataset])
    run_step("Step 2: ONNX → RKNN", onnx_to_rknn)

    print(f"\n{'='*60}")
    print(f"  Pipeline complete!")
    print(f"  ONNX: {onnx_path}")
    print(f"  RKNN: {args.output}")
    rknn_size = os.path.getsize(args.output) / (1024 * 1024)
    print(f"  Size: {rknn_size:.1f} MB")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
