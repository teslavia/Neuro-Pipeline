"""Dashboard conftest — add repo root to sys.path for imports."""
import sys
from pathlib import Path

# Add repo root so `extensions.dashboard.app` and `mac-central/src/` are importable
repo_root = Path(__file__).resolve().parents[3]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))
mac_central_src = repo_root / "mac-central" / "src"
if str(mac_central_src) not in sys.path:
    sys.path.insert(0, str(mac_central_src))
