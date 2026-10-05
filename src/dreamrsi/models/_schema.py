"""Validation shared by versioned JSON data loaders."""

from __future__ import annotations

from typing import Any


def validate_schema(data: dict[str, Any], model_name: str) -> None:
    """Accept unversioned legacy data, but never guess future schema semantics."""
    if not isinstance(data, dict):
        raise ValueError(f"{model_name} data must be a JSON object")
    if "_schema_version" not in data:
        return
    version = data["_schema_version"]
    if not isinstance(version, str) or version != "1":
        raise ValueError(f"Unsupported {model_name} schema version: {version!r}")
