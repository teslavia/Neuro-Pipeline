"""Generic dataclass loader from dict — replaces repetitive .get() chains."""

import dataclasses
from typing import Any, List, get_type_hints, get_origin, get_args


def load_dataclass_from_dict(cls, data: dict) -> Any:
    """Recursively populate a dataclass from a dict.

    Supports:
    - Nested dataclasses
    - List[T] where T is a dataclass
    - Type coercion for int, float, bool, str
    - Missing keys fall back to dataclass field defaults
    """
    if not data or not isinstance(data, dict):
        return cls()

    hints = get_type_hints(cls)
    kwargs = {}

    for f in dataclasses.fields(cls):
        name = f.name
        if name not in data:
            continue

        raw = data[name]
        field_type = hints.get(name, f.type)

        kwargs[name] = _coerce_value(raw, field_type)

    return cls(**kwargs)


def _coerce_value(raw: Any, field_type: Any) -> Any:
    """Coerce a raw value to the expected field type."""
    origin = get_origin(field_type)
    args = get_args(field_type)

    # List[T]
    if origin is list and args and isinstance(raw, list):
        inner = args[0]
        if dataclasses.is_dataclass(inner):
            return [load_dataclass_from_dict(inner, item) for item in raw if isinstance(item, dict)]
        return [_coerce_scalar(item, inner) for item in raw]

    # Nested dataclass
    if dataclasses.is_dataclass(field_type) and isinstance(raw, dict):
        return load_dataclass_from_dict(field_type, raw)

    return _coerce_scalar(raw, field_type)


def _coerce_scalar(raw: Any, target_type: Any) -> Any:
    """Coerce a scalar value to the target type."""
    if raw is None:
        return raw

    try:
        if target_type is bool:
            return bool(raw)
        if target_type is int:
            return int(raw)
        if target_type is float:
            return float(raw)
        if target_type is str:
            return str(raw)
    except (ValueError, TypeError):
        return raw

    return raw
