"""Backward-compatible wrapper around generic schema mapping.

This module name is retained to avoid broad import churn while phase-1 agnostic
hardening is rolled out.
"""

from typing import Any

from app.services.schema_mapping import category_for_column, map_schema_columns


def map_cultivation_columns(columns: list[str]) -> dict[str, Any]:
    """Compatibility alias. Returns generic schema mapping payload."""
    return map_schema_columns(columns)
