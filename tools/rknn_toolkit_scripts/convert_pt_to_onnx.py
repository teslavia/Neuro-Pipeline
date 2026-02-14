#!/usr/bin/env python3
"""
PyTorch (.pt) → ONNX conversion script for YOLOv5 models.

Usage:
    python convert_pt_to_onnx.py --weights yolov5s.pt --output yolov5s.onnx
    python convert_pt_to_onnx.py --weights yolov5s.pt --output yolov5s.onnx --img-size 640 --simplify

Requires: torch, onnx, onnxsim (optional)
"""

import argparse
import sys


def convert(args):
    try:
        import torch
    except ImportError:
        print("ERROR: PyTorch not installed. pip install torch")
        sys.exit(1)

    print(f"[1/3] Loading PyTorch model: {args.weights}")
    model = torch.load(args.weights, map_location="cpu")

    # Handle YOLOv5 checkpoint format
    if isinstance(model, dict):
        if "model" in model:
            model = model["model"].float()
        elif "ema" in model and model["ema"] is not None:
            model = model["ema"].float()
    model.eval()

    # Create dummy input
    img_size = args.img_size
    dummy_input = torch.randn(1, 3, img_size, img_size)

    print(f"[2/3] Exporting to ONNX (opset={args.opset})...")
    torch.onnx.export(
        model,
        dummy_input,
        args.output,
        opset_version=args.opset,
        input_names=["images"],
        output_names=["output0", "output1", "output2"],
        dynamic_axes=None,  # Fixed shape for RKNN
    )
    print(f"Exported: {args.output}")

    # Optional: simplify with onnx-simplifier
    if args.simplify:
        try:
            import onnx
            from onnxsim import simplify

            print("[3/3] Simplifying ONNX model...")
            model_onnx = onnx.load(args.output)
            model_simplified, check = simplify(model_onnx)
            if check:
                onnx.save(model_simplified, args.output)
                print("Simplified successfully")
            else:
                print("WARNING: Simplification check failed, keeping original")
        except ImportError:
            print("WARNING: onnxsim not installed, skipping simplification")
            print("Install: pip install onnx-simplifier")
    else:
        print("[3/3] Skipping simplification (use --simplify to enable)")

    print(f"Done. Output: {args.output}")


def main():
    parser = argparse.ArgumentParser(description="Convert PyTorch model to ONNX")
    parser.add_argument("--weights", required=True, help="Input .pt model path")
    parser.add_argument("--output", required=True, help="Output .onnx model path")
    parser.add_argument("--img-size", type=int, default=640,
                        help="Input image size (default: 640)")
    parser.add_argument("--opset", type=int, default=12,
                        help="ONNX opset version (default: 12)")
    parser.add_argument("--simplify", action="store_true",
                        help="Simplify ONNX model with onnx-simplifier")
    args = parser.parse_args()
    convert(args)


if __name__ == "__main__":
    main()
