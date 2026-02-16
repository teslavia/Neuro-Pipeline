"""Conftest for e2e/chaos tests — add mac-central/src to sys.path."""
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
mac_src = repo_root / "mac-central" / "src"
if str(mac_src) not in sys.path:
    sys.path.insert(0, str(mac_src))
