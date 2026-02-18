"""Unified version management for Neuro-Pipeline.

This module provides a single source of truth for version information,
reading from VERSION.json at the repository root.
"""

import json
from pathlib import Path
from typing import Optional

# Path to VERSION.json (repo root / mac-central / src / core)
_VERSION_FILE = Path(__file__).parent.parent.parent.parent / "VERSION.json"

# Cached version data
_version_data: Optional[dict] = None


def _load_version_data() -> dict:
    """Load version data from VERSION.json."""
    global _version_data
    if _version_data is None:
        try:
            with open(_VERSION_FILE) as f:
                _version_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            _version_data = {"version": "0.0.0", "name": "neuro-pipeline"}
    return _version_data


def get_version() -> str:
    """Get the current version string."""
    return _load_version_data().get("version", "0.0.0")


def get_name() -> str:
    """Get the project name."""
    return _load_version_data().get("name", "neuro-pipeline")


def get_milestone() -> str:
    """Get the current milestone description."""
    return _load_version_data().get("milestone", "")


def get_component_version(component: str) -> str:
    """Get version for a specific component (e.g., 'rk3588-edge', 'mac-central')."""
    components = _load_version_data().get("components", {})
    return components.get(component, "0.0.0")


def get_full_info() -> dict:
    """Get full version information."""
    return _load_version_data().copy()


# Module-level version constant (for convenience)
__version__ = get_version()
__name__ = get_name()
