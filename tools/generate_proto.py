#!/usr/bin/env python3
"""
Generate C++ and Python code from protobuf definitions.

Usage:
    python3 tools/generate_proto.py
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PROTO_DIR = REPO_ROOT / "proto"
PROTO_FILE = PROTO_DIR / "neuro_pipeline.proto"

# Output directories
CPP_OUT = REPO_ROOT / "rk3588-edge" / "src" / "generated"
PYTHON_OUT = REPO_ROOT / "mac-central" / "src" / "generated"


def run_command(cmd: list[str], description: str) -> bool:
    """Run shell command with error handling."""
    print(f"[INFO] {description}...")
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"[OK]   {description} complete")
        return True
    except FileNotFoundError as e:
        print(f"[SKIP] {description}: tool not found ({e.filename})")
        return False
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] {description} failed:")
        print(e.stderr)
        return False


def generate_python() -> bool:
    """Generate Python protobuf and gRPC code."""
    PYTHON_OUT.mkdir(parents=True, exist_ok=True)

    success = run_command(
        [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            f"--proto_path={PROTO_DIR}",
            f"--python_out={PYTHON_OUT}",
            f"--pyi_out={PYTHON_OUT}",
            f"--grpc_python_out={PYTHON_OUT}",
            str(PROTO_FILE),
        ],
        "Generating Python protobuf + gRPC code",
    )

    if success:
        # Ensure __init__.py exists
        init_file = PYTHON_OUT / "__init__.py"
        if not init_file.exists():
            init_file.write_text('"""Generated protobuf code."""\n')

    return success


def generate_cpp() -> bool:
    """Generate C++ protobuf and gRPC code."""
    CPP_OUT.mkdir(parents=True, exist_ok=True)

    # Find grpc_cpp_plugin
    import shutil

    grpc_plugin = shutil.which("grpc_cpp_plugin")

    if not grpc_plugin:
        print("[SKIP] grpc_cpp_plugin not found - C++ gRPC code not generated")
        # Still try plain protobuf
        return run_command(
            [
                "protoc",
                f"--proto_path={PROTO_DIR}",
                f"--cpp_out={CPP_OUT}",
                str(PROTO_FILE),
            ],
            "Generating C++ protobuf code (without gRPC)",
        )

    return run_command(
        [
            "protoc",
            f"--proto_path={PROTO_DIR}",
            f"--cpp_out={CPP_OUT}",
            f"--grpc_out={CPP_OUT}",
            f"--plugin=protoc-gen-grpc={grpc_plugin}",
            str(PROTO_FILE),
        ],
        "Generating C++ protobuf + gRPC code",
    )


def main() -> None:
    print("=" * 60)
    print("  Neuro-Pipeline Protobuf Code Generator")
    print("=" * 60)
    print(f"Proto file: {PROTO_FILE}")
    print(f"C++ output: {CPP_OUT}")
    print(f"Python output: {PYTHON_OUT}")
    print()

    if not PROTO_FILE.exists():
        print(f"[ERROR] Proto file not found: {PROTO_FILE}")
        sys.exit(1)

    py_ok = generate_python()
    cpp_ok = generate_cpp()

    print()
    if py_ok or cpp_ok:
        print("[SUCCESS] Code generation completed!")
        if py_ok:
            print(f"  Python: {PYTHON_OUT}")
        if cpp_ok:
            print(f"  C++:    {CPP_OUT}")
    else:
        print("[WARNING] No code was generated. Install dependencies:")
        print("  pip install grpcio-tools   # For Python")
        print("  brew install protobuf grpc # For C++ (macOS)")
        sys.exit(1)


if __name__ == "__main__":
    main()
